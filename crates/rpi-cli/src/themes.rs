//! Theme spec resolution and loading.
//!
//! A *theme spec* is the value of `--theme` / `settings.json.theme`: either a
//! built-in preset name (`dark` / `light` / `monochrome`) or a path to a pi
//! theme JSON file (`ThemeJson`, see `rpi_tui::theme_json`). File specs expand
//! `~` and load lazily at the point of application so parse errors surface as
//! warnings plus a fallback to the built-in default, never a startup veto —
//! the same gentle style as `emit_startup_warnings`.
//!
//! `--no-themes` is enforced upstream (`app.rs` passes no theme at all), so
//! custom files cannot bypass it here.

use std::path::{Path, PathBuf};

use rpi_tui::theme::{global_theme_manager, Theme, ThemeManager, ThemePreset};
use rpi_tui::theme_json::ThemeJson;

/// A resolved theme spec: built-in preset or theme file path.
#[derive(Debug, Clone)]
pub enum ThemeSpec {
    Preset(ThemePreset),
    File(PathBuf),
}

/// Classify a theme spec string. Anything that is not a built-in preset name
/// is treated as a file path (the documented `--theme` semantics).
pub fn resolve_spec(value: &str) -> ThemeSpec {
    match value {
        "dark" => ThemeSpec::Preset(ThemePreset::Dark),
        "light" => ThemeSpec::Preset(ThemePreset::Light),
        "monochrome" => ThemeSpec::Preset(ThemePreset::Monochrome),
        other => ThemeSpec::File(expand_home(other)),
    }
}

/// Expand a leading `~` to the user's home directory. `~user` forms are left
/// untouched (only the current user's home is resolvable here).
pub fn expand_home(value: &str) -> PathBuf {
    if value == "~" {
        if let Some(home) = dirs::home_dir() {
            return home;
        }
    } else if let Some(rest) = value.strip_prefix("~/") {
        if let Some(home) = dirs::home_dir() {
            return home.join(rest);
        }
    }
    PathBuf::from(value)
}

/// A successfully loaded file theme, ready to apply.
#[derive(Debug, Clone)]
pub struct LoadedTheme {
    /// Theme name from the JSON (`name` field), for messages.
    pub name: String,
    /// The parsed theme (default spacing/border styles).
    pub theme: Theme,
    /// The file it came from, for diagnostics.
    pub source: PathBuf,
}

impl LoadedTheme {
    /// Parse a pi theme file. The error message includes the path and reason.
    pub fn load(path: &Path) -> Result<Self, String> {
        let json = ThemeJson::from_file(path)
            .map_err(|e| format!("cannot load theme {}: {e}", path.display()))?;
        let theme = json
            .to_theme()
            .map_err(|e| format!("cannot load theme {}: {e}", path.display()))?;
        Ok(Self {
            name: json.name,
            theme,
            source: path.to_path_buf(),
        })
    }
}

/// Apply a file theme to both the process-wide theme (what components read)
/// and the session's theme manager (what `/theme` swaps), mirroring the
/// preset path's dual application.
pub fn apply_loaded(loaded: &LoadedTheme, session_manager: &ThemeManager) {
    global_theme_manager().set(loaded.theme.clone());
    session_manager.set(loaded.theme.clone());
}

/// Resolve + apply a theme spec at TUI startup.
///
/// Returns `Err(message)` when a file spec fails to load; the caller falls
/// back to the built-in default (no theme is applied) and surfaces the
/// message as a warning.
pub fn apply_spec(spec: &ThemeSpec, session_manager: &ThemeManager) -> Result<(), String> {
    match spec {
        ThemeSpec::Preset(preset) => {
            session_manager.apply_preset(*preset);
            rpi_tui::theme::apply_theme_preset(*preset);
            Ok(())
        }
        ThemeSpec::File(path) => match LoadedTheme::load(path) {
            Ok(loaded) => {
                apply_loaded(&loaded, session_manager);
                Ok(())
            }
            Err(message) => Err(message),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rpi_tui::theme::ThemeColors;

    fn temp_theme_file(dir: &Path, name: &str, accent: &str) -> PathBuf {
        let path = dir.join(name);
        std::fs::write(
            &path,
            format!(r##"{{"name":"{name}","colors":{{"accent":"{accent}"}}}}"##),
        )
        .unwrap();
        path
    }

    #[test]
    fn preset_names_classify_to_presets() {
        assert!(matches!(
            resolve_spec("dark"),
            ThemeSpec::Preset(ThemePreset::Dark)
        ));
        assert!(matches!(
            resolve_spec("light"),
            ThemeSpec::Preset(ThemePreset::Light)
        ));
        assert!(matches!(
            resolve_spec("monochrome"),
            ThemeSpec::Preset(ThemePreset::Monochrome)
        ));
        // Case-sensitive: preset names are lowercase identifiers.
        assert!(matches!(resolve_spec("Dark"), ThemeSpec::File(_)));
    }

    #[test]
    fn everything_else_is_a_file_path() {
        assert!(matches!(
            resolve_spec("themes/ocean.json"),
            ThemeSpec::File(ref p) if p == &PathBuf::from("themes/ocean.json")
        ));
        assert!(matches!(
            resolve_spec("~/.rpi/agent/themes/ocean.json"),
            ThemeSpec::File(ref p) if *p == expand_home("~/.rpi/agent/themes/ocean.json")
        ));
    }

    #[test]
    fn expand_home_forms() {
        let home = dirs::home_dir().unwrap();
        assert_eq!(expand_home("~"), home);
        assert_eq!(expand_home("~/x.json"), home.join("x.json"));
        assert_eq!(expand_home("/tmp/x.json"), PathBuf::from("/tmp/x.json"));
        assert_eq!(expand_home("x.json"), PathBuf::from("x.json"));
        // ~user is not expanded (only the current user's home is resolvable).
        assert_eq!(expand_home("~root/x.json"), PathBuf::from("~root/x.json"));
    }

    #[test]
    fn load_file_theme_end_to_end() {
        let dir = std::env::temp_dir().join(format!("rpi-theme-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = temp_theme_file(&dir, "ocean.json", "#3366ff");
        let loaded = LoadedTheme::load(&path).unwrap();
        assert_eq!(loaded.name, "ocean.json");
        assert_eq!(
            loaded.theme.colors.accent,
            rpi_tui::theme::Color::Rgb(51, 102, 255)
        );
        // Everything else stays at the default palette.
        assert_eq!(
            loaded.theme.colors.md_heading,
            ThemeColors::default().md_heading
        );
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn load_failure_message_contains_path_and_reason() {
        let dir = std::env::temp_dir().join(format!("rpi-theme-bad-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("broken.json");
        std::fs::write(&path, r#"{"name":"broken","colors":{"accent":"nope"}}"#).unwrap();
        let err = LoadedTheme::load(&path).unwrap_err();
        assert!(err.contains("broken.json"), "{err}");
        assert!(err.contains("nope"), "{err}");

        let missing = dir.join("missing.json");
        let err = LoadedTheme::load(&missing).unwrap_err();
        assert!(err.contains("missing.json"), "{err}");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn apply_spec_preset_and_file_and_failure() {
        let manager = ThemeManager::new();
        let revision_before = rpi_tui::theme::theme_revision();

        // Preset applies to both managers.
        apply_spec(&ThemeSpec::Preset(ThemePreset::Light), &manager).unwrap();
        assert!(matches!(
            manager.get().colors.muted,
            rpi_tui::theme::Color::Ansi256(241)
        ));

        // File spec applies the parsed colors.
        let dir = std::env::temp_dir().join(format!("rpi-theme-apply-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = temp_theme_file(&dir, "ocean.json", "#ff0000");
        apply_spec(&ThemeSpec::File(path.clone()), &manager).unwrap();
        assert_eq!(
            manager.get().colors.accent,
            rpi_tui::theme::Color::Rgb(255, 0, 0)
        );
        assert_eq!(
            global_theme_manager().get().colors.accent,
            rpi_tui::theme::Color::Rgb(255, 0, 0)
        );

        // Failed file spec returns the message; managers keep the last theme.
        let err = apply_spec(&ThemeSpec::File(dir.join("missing.json")), &manager).unwrap_err();
        assert!(err.contains("missing.json"), "{err}");
        assert_eq!(
            manager.get().colors.accent,
            rpi_tui::theme::Color::Rgb(255, 0, 0)
        );

        assert!(rpi_tui::theme::theme_revision() > revision_before);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn loaded_theme_load_parses_without_applying() {
        // Note: global-manager side effects cannot be observed reliably from a
        // parallel test suite (sibling tests share the process-wide manager),
        // so this only pins that loading produces the parsed colors; by
        // construction `LoadedTheme::load` touches no manager.
        let dir = std::env::temp_dir().join(format!("rpi-theme-prev-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = temp_theme_file(&dir, "solo.json", "#00ff00");
        let loaded = LoadedTheme::load(&path).unwrap();
        assert_eq!(
            loaded.theme.colors.accent,
            rpi_tui::theme::Color::Rgb(0, 255, 0)
        );
        std::fs::remove_dir_all(&dir).ok();
    }
}
