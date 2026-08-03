#!/usr/bin/env python3
"""Apply the controlled cat descriptor-classification candidate.

All replacements are exact or marker-bounded and fail closed on source drift.
"""

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement site, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: Path, start: str, end: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise SystemExit(f"{path}: marker count changed")
    start_pos = text.index(start)
    end_pos = text.index(end, start_pos)
    path.write_text(text[:start_pos] + replacement + text[end_pos:], encoding="utf-8")


cat = Path("src/uu/cat/src/cat.rs")
replace_between(
    cat,
    '''/// Concrete enum of recognized file types.
''',
    '''mod options {
''',
    '',
)
replace_between(
    cat,
    '''fn cat_path(path: &OsString, options: &OutputOptions, state: &mut OutputState) -> CatResult<()> {
''',
    '''/// Writes handle to stdout with no configuration. This allows a
''',
    '''#[cfg(unix)]
fn map_open_error(path: &OsString, error: io::Error) -> CatError {
    // Successful inputs are classified from their opened descriptor. A failed
    // open consumes no file, so a path lookup here is used only to preserve the
    // established cross-Unix socket diagnostic.
    if metadata(path).is_ok_and(|metadata| metadata.file_type().is_socket()) {
        return CatError::NoSuchDeviceOrAddress;
    }

    #[cfg(not(any(target_os = "macos", target_os = "freebsd")))]
    let too_many_symlink_code = 40;
    #[cfg(any(target_os = "macos", target_os = "freebsd"))]
    let too_many_symlink_code = 62;
    if error.raw_os_error() == Some(too_many_symlink_code) {
        CatError::TooManySymlinks
    } else {
        error.into()
    }
}

#[cfg(unix)]
fn ensure_open_input_supported(file: &File) -> CatResult<()> {
    let file_type = file.metadata()?.file_type();
    if file_type.is_dir() {
        Err(CatError::IsDirectory)
    } else if file_type.is_file()
        || file_type.is_fifo()
        || file_type.is_char_device()
        || file_type.is_block_device()
    {
        Ok(())
    } else {
        Err(CatError::UnknownFiletype {
            ft_debug: format!("{file_type:?}"),
        })
    }
}

#[cfg(not(unix))]
fn ensure_open_input_supported(file: &File) -> CatResult<()> {
    let file_type = file.metadata()?.file_type();
    if file_type.is_dir() {
        Err(CatError::IsDirectory)
    } else if file_type.is_file() {
        Ok(())
    } else {
        Err(CatError::UnknownFiletype {
            ft_debug: format!("{file_type:?}"),
        })
    }
}

#[cfg(unix)]
fn open_input(path: &OsString) -> CatResult<File> {
    let file = File::open(path).map_err(|error| map_open_error(path, error))?;
    ensure_open_input_supported(&file)?;
    Ok(file)
}

#[cfg(not(unix))]
fn open_input(path: &OsString) -> CatResult<File> {
    // Some non-Unix platforms do not permit opening a directory as a regular
    // file. Preserve the established "Is a directory" diagnostic there.
    if metadata(path)?.is_dir() {
        return Err(CatError::IsDirectory);
    }
    let file = File::open(path)?;
    ensure_open_input_supported(&file)?;
    Ok(file)
}

fn cat_path(path: &OsString, options: &OutputOptions, state: &mut OutputState) -> CatResult<()> {
    if path == "-" {
        let stdin = io::stdin();
        let is_interactive = stdin.is_terminal();
        if !is_safe_overwrite(&stdin, &io::stdout()) {
            return Err(CatError::OutputIsInput);
        }
        let mut handle = InputHandle {
            reader: stdin,
            is_interactive,
        };
        return cat_handle(&mut handle, options, state);
    }

    // Open once, then classify and read that same file descriptor. This keeps
    // a path replacement from making the type check describe a different file
    // than the one whose contents are consumed.
    let file = open_input(path)?;
    if !is_safe_overwrite(&file, &io::stdout()) {
        return Err(CatError::OutputIsInput);
    }
    let mut handle = InputHandle {
        reader: file,
        is_interactive: false,
    };
    cat_handle(&mut handle, options, state)
}

fn cat_files<'a, I>(files: I, options: &OutputOptions) -> UResult<()>
where
    I: IntoIterator<Item = &'a OsString>,
{
    let mut state = OutputState {
        line_number: LineNumber::new(),
        at_line_start: true,
        skipped_carriage_return: false,
        one_blank_kept: false,
    };
    let mut error_messages: Vec<String> = Vec::new();

    for path in files {
        if let Err(err) = cat_path(path, options, &mut state) {
            error_messages.push(format!("{}: {err}", path.maybe_quote()));
        }
    }
    if state.skipped_carriage_return {
        print!("\\r");
    }
    if error_messages.is_empty() {
        Ok(())
    } else {
        // each next line is expected to display "cat: …"
        let line_joiner = "\\ncat: ";

        Err(uucore::error::USimpleError::new(
            error_messages.len() as i32,
            error_messages.join(line_joiner),
        ))
    }
}

''',
)
replace_once(
    cat,
    '''#[cfg(test)]
mod tests {
    use std::io::{BufWriter, stdout};

''',
    '''#[cfg(test)]
mod tests {
    use std::io::{BufWriter, stdout};

    #[cfg(unix)]
    #[test]
    fn opened_input_classification_survives_path_replacement() {
        use std::fs::{self, File};
        use tempfile::tempdir;

        let temp = tempdir().unwrap();
        let path = temp.path().join("input");
        let moved = temp.path().join("opened-input");
        fs::write(&path, b"content").unwrap();
        let file = File::open(&path).unwrap();

        fs::rename(&path, &moved).unwrap();
        fs::create_dir(&path).unwrap();

        assert!(super::ensure_open_input_supported(&file).is_ok());
        assert!(file.metadata().unwrap().is_file());
        assert!(path.is_dir());
    }

''',
)
