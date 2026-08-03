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
replace_once(
    cat,
    '''use std::ffi::OsString;
use std::fs::{File, metadata};
use std::io::{self, BufWriter, ErrorKind, IsTerminal, Read, Write};
#[cfg(any(unix, target_os = "wasi"))]
use std::os::fd::AsFd;
#[cfg(unix)]
use std::os::unix::fs::FileTypeExt;
use thiserror::Error;
''',
    '''use std::ffi::OsString;
use std::fs::File;
#[cfg(not(unix))]
use std::fs::metadata;
use std::io::{self, BufWriter, ErrorKind, IsTerminal, Read, Write};
#[cfg(any(unix, target_os = "wasi"))]
use std::os::fd::AsFd;
use thiserror::Error;
''',
)
replace_once(
    cat,
    '''    /// Unknown file type; it's not a regular file, socket, etc.
    #[error("{}", translate!("cat-error-unknown-filetype", "ft_debug" => .ft_debug))]
    UnknownFiletype {
        /// A debug print of the file type
        ft_debug: String,
    },
    #[error("{}", translate!("cat-error-is-directory"))]
    IsDirectory,
    #[cfg(unix)]
    #[error("{}", translate!("cat-error-no-such-device-or-address"))]
    NoSuchDeviceOrAddress,
    #[error("{}", translate!("cat-error-input-file-is-output-file"))]
    OutputIsInput,
    #[error("{}", translate!("cat-error-too-many-symbolic-links"))]
    TooManySymlinks,
''',
    '''    #[error("{}", translate!("cat-error-is-directory"))]
    IsDirectory,
    #[error("{}", translate!("cat-error-input-file-is-output-file"))]
    OutputIsInput,
''',
)
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
fn ensure_open_input_is_not_directory(file: &File) -> CatResult<()> {
    if file.metadata()?.is_dir() {
        Err(CatError::IsDirectory)
    } else {
        Ok(())
    }
}

#[cfg(unix)]
fn open_input(path: &OsString) -> CatResult<File> {
    let file = File::open(path)?;
    ensure_open_input_is_not_directory(&file)?;
    Ok(file)
}

#[cfg(not(unix))]
fn open_input(path: &OsString) -> CatResult<File> {
    // Some non-Unix platforms do not permit opening a directory as a regular
    // file. Preserve the established "Is a directory" diagnostic there.
    if metadata(path)?.is_dir() {
        return Err(CatError::IsDirectory);
    }
    Ok(File::open(path)?)
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

        assert!(super::ensure_open_input_is_not_directory(&file).is_ok());
        assert!(file.metadata().unwrap().is_file());
        assert!(path.is_dir());
    }

''',
)

tests = Path("tests/by-util/test_cat.rs")
replace_once(
    tests,
    '''#[cfg(unix)]
use std::fs::File;
use std::fs::OpenOptions;
''',
    '''#[cfg(unix)]
use std::fs::File;
use std::fs::OpenOptions;
#[cfg(unix)]
use std::os::unix::net::UnixListener;
''',
)
replace_once(
    tests,
    '''#[test]
fn test_directory_and_file() {
''',
    '''#[test]
#[cfg(unix)]
fn test_socket_reports_open_error() {
    let scene = TestScenario::new(util_name!());
    let socket = scene.fixtures.plus("socket");
    let _listener = UnixListener::bind(&socket).unwrap();

    scene
        .ucmd()
        .arg("socket")
        .fails()
        .stderr_is("cat: socket: No such device or address\\n");
}

#[test]
#[cfg(unix)]
fn test_symlink_loop_reports_open_error() {
    let scene = TestScenario::new(util_name!());
    scene.fixtures.symlink_file("loop-b", "loop-a");
    scene.fixtures.symlink_file("loop-a", "loop-b");

    scene
        .ucmd()
        .arg("loop-a")
        .fails()
        .stderr_is("cat: loop-a: Too many levels of symbolic links\\n");
}

#[test]
fn test_directory_and_file() {
''',
)
