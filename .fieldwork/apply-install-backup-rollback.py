#!/usr/bin/env python3
"""Apply the controlled install backup-rollback candidate.

The script uses exact, single-occurrence replacements so a changed source
layout fails closed instead of silently applying to the wrong code.
"""

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement site, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


install = Path("src/uu/install/src/install.rs")
replace_once(
    install,
    '''    #[error("{}", translate!("install-error-backup-failed", "from" => .0.quote(), "error" => strip_errno(.1)))]
    BackupFailed(PathBuf, #[source] std::io::Error),

''',
    '''    #[error("{}", translate!("install-error-backup-failed", "from" => .0.quote(), "error" => strip_errno(.1)))]
    BackupFailed(PathBuf, #[source] std::io::Error),

    #[error("{}", translate!("install-error-restore-backup-failed", "backup" => .0.quote(), "dest" => .1.quote(), "error" => strip_errno(.2)))]
    RestoreBackupFailed(PathBuf, PathBuf, #[source] std::io::Error),

''',
)

replace_once(
    install,
    '''fn perform_backup(from: &Path, to: &Path, b: &Behavior) -> UResult<Option<PathBuf>> {
    // Renaming the destination over the source would leave nothing to install
    // from, so refuse instead.
    if backup_would_destroy_source(from, to, &b.suffix, b.backup_mode, true) {
        return Err(
            InstallError::BackupWouldDestroySource(to.to_path_buf(), from.to_path_buf()).into(),
        );
    }

    if to.exists() {
        if b.verbose {
            writeln!(
                stdout(),
                "{}",
                translate!("install-verbose-removed", "path" => to.quote())
            )?;
        }
        let backup_path = backup_control::get_backup_path(b.backup_mode, to, &b.suffix);
        if let Some(ref backup_path) = backup_path {
            fs::rename(to, backup_path)
                .map_err(|err| InstallError::BackupFailed(to.to_path_buf(), err))?;
        }
        Ok(backup_path)
    } else {
        Ok(None)
    }
}

''',
    '''fn perform_backup(from: &Path, to: &Path, b: &Behavior) -> UResult<Option<PathBuf>> {
    // Renaming the destination over the source would leave nothing to install
    // from, so refuse instead.
    if backup_would_destroy_source(from, to, &b.suffix, b.backup_mode, true) {
        return Err(
            InstallError::BackupWouldDestroySource(to.to_path_buf(), from.to_path_buf()).into(),
        );
    }

    if to.exists() {
        if b.verbose {
            writeln!(
                stdout(),
                "{}",
                translate!("install-verbose-removed", "path" => to.quote())
            )?;
        }
        let backup_path = backup_control::get_backup_path(b.backup_mode, to, &b.suffix);
        if let Some(ref backup_path) = backup_path {
            fs::rename(to, backup_path)
                .map_err(|err| InstallError::BackupFailed(to.to_path_buf(), err))?;
        }
        Ok(backup_path)
    } else {
        Ok(None)
    }
}

/// Restore a destination that was renamed aside before the data copy failed.
///
/// GNU install rolls this pre-copy backup transaction back: any partial
/// destination is removed and the backup is renamed to the original path.
fn restore_backup_after_copy_failure(to: &Path, backup_path: &Path) -> UResult<()> {
    match fs::remove_file(to) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => {
            return Err(InstallError::RestoreBackupFailed(
                backup_path.to_path_buf(),
                to.to_path_buf(),
                error,
            )
            .into());
        }
    }

    fs::rename(backup_path, to).map_err(|error| {
        InstallError::RestoreBackupFailed(
            backup_path.to_path_buf(),
            to.to_path_buf(),
            error,
        )
        .into()
    })
}

''',
)

replace_once(
    install,
    '''    let backup_path = perform_backup(from, to, b)?;

    copy_file(from, to)?;

    finalize_installed_file(from, to, b, backup_path)
''',
    '''    let backup_path = perform_backup(from, to, b)?;

    if let Err(copy_error) = copy_file(from, to) {
        // An empty suffix currently produces the destination path itself as the
        // nominal backup path. No separate backup exists in that case, so keep
        // the pre-existing behavior and leave it to the empty-suffix fix.
        if let Some(ref backup_path) = backup_path
            && backup_path != to
            && let Err(restore_error) = restore_backup_after_copy_failure(to, backup_path)
        {
            show!(copy_error);
            return Err(restore_error);
        }
        return Err(copy_error);
    }

    finalize_installed_file(from, to, b, backup_path)
''',
)

replace_once(
    Path("src/uu/install/locales/en-US.ftl"),
    "install-error-backup-failed = cannot backup { $from }: { $error }\n",
    "install-error-backup-failed = cannot backup { $from }: { $error }\n"
    "install-error-restore-backup-failed = cannot restore backup { $backup } to { $dest }: { $error }\n",
)

replace_once(
    Path("src/uu/install/locales/fr-FR.ftl"),
    "install-error-backup-failed = impossible de sauvegarder { $from } : { $error }\n",
    "install-error-backup-failed = impossible de sauvegarder { $from } : { $error }\n"
    "install-error-restore-backup-failed = impossible de restaurer la sauvegarde { $backup } vers { $dest } : { $error }\n",
)

replace_once(
    Path("tests/by-util/test_install.rs"),
    '''#[test]
fn test_install_backup_nil_same_file() {
''',
    '''#[test]
#[cfg(target_os = "linux")]
fn test_install_restores_destination_after_copy_error_with_backup() {
    for mode in ["simple", "existing", "numbered"] {
        let scene = TestScenario::new(util_name!());
        let at = &scene.fixtures;

        at.mkdir_all("source");
        at.mkdir("dest");
        std::os::unix::fs::symlink("/proc/self/mem", at.plus("source/file")).unwrap();
        at.write("dest/file", "original");

        scene
            .ucmd()
            .arg(format!("--backup={mode}"))
            .arg("source/file")
            .arg("dest/file")
            .fails()
            .stderr_contains("Input/output error");

        assert_eq!(at.read("dest/file"), "original");
        assert!(!at.file_exists("dest/file~"));
        assert!(!at.file_exists("dest/file.~1~"));
    }
}

#[test]
#[cfg(target_os = "linux")]
fn test_install_copy_error_rollback_preserves_original_backup_for_later_source() {
    let scene = TestScenario::new(util_name!());
    let at = &scene.fixtures;

    at.mkdir_all("source1");
    at.mkdir_all("source2");
    at.mkdir("dest");
    std::os::unix::fs::symlink("/proc/self/mem", at.plus("source1/file")).unwrap();
    at.write("source2/file", "second");
    at.write("dest/file", "original");

    scene
        .ucmd()
        .arg("--backup=simple")
        .arg("-t")
        .arg("dest")
        .arg("source1/file")
        .arg("source2/file")
        .fails()
        .stderr_contains("Input/output error");

    assert_eq!(at.read("dest/file"), "second");
    assert_eq!(at.read("dest/file~"), "original");
}

#[test]
#[cfg(target_os = "linux")]
fn test_install_copy_error_rollback_preserves_existing_numbered_backup() {
    let scene = TestScenario::new(util_name!());
    let at = &scene.fixtures;

    at.mkdir_all("source");
    at.mkdir("dest");
    std::os::unix::fs::symlink("/proc/self/mem", at.plus("source/file")).unwrap();
    at.write("dest/file", "original");
    at.write("dest/file.~1~", "older");

    scene
        .ucmd()
        .arg("--backup=existing")
        .arg("source/file")
        .arg("dest/file")
        .fails()
        .stderr_contains("Input/output error");

    assert_eq!(at.read("dest/file"), "original");
    assert_eq!(at.read("dest/file.~1~"), "older");
    assert!(!at.file_exists("dest/file.~2~"));
}

#[test]
fn test_install_backup_nil_same_file() {
''',
)
