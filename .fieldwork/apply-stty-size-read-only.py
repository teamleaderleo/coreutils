#!/usr/bin/env python3
"""Apply the controlled stty print-only tcsetattr candidate."""

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement site, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


source = Path("src/uu/stty/src/stty.rs")
replace_once(
    source,
    '''enum ArgOptions<'a> {
    Flags(AllFlags<'a>),
    Mapping((S, u8)),
    Special(SpecialSetting),
    Print(PrintSetting),
    SavedState(Vec<u32>),
}

''',
    '''enum ArgOptions<'a> {
    Flags(AllFlags<'a>),
    Mapping((S, u8)),
    Special(SpecialSetting),
    Print(PrintSetting),
    SavedState(Vec<u32>),
}

fn requires_set_attr(args: &[ArgOptions<'_>]) -> bool {
    args.iter().any(|arg| !matches!(arg, ArgOptions::Print(_)))
}

''',
)
replace_once(
    source,
    '''        tcsetattr(opts.file.as_fd(), set_arg, &termios)?;
''',
    '''        if requires_set_attr(&valid_args) {
            tcsetattr(opts.file.as_fd(), set_arg, &termios)?;
        }
''',
)
replace_once(
    source,
    '''    // Essential unit tests for complex internal parsing and logic functions.

''',
    '''    // Essential unit tests for complex internal parsing and logic functions.

    #[test]
    fn print_only_actions_do_not_require_tcsetattr() {
        assert!(!requires_set_attr(&[ArgOptions::Print(PrintSetting::Size)]));
        assert!(requires_set_attr(&[ArgOptions::Special(
            SpecialSetting::Rows(24),
        )]));
        assert!(requires_set_attr(&[
            ArgOptions::Print(PrintSetting::Size),
            ArgOptions::Special(SpecialSetting::Cols(80)),
        ]));
    }

''',
)
