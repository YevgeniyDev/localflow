#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{Manager};
use tauri_plugin_global_shortcut::{Shortcut, ShortcutState, GlobalShortcutExt};

fn main() {
  tauri::Builder::default()
    .plugin(tauri_plugin_global_shortcut::init())
    .setup(|app| {
      let handle = app.handle();

      // Ctrl+Space toggles overlay
      let shortcut: Shortcut = "Ctrl+Space".parse().expect("invalid shortcut");

      app.global_shortcut().on_shortcut(shortcut.clone(), move |event| {
        if event.state == ShortcutState::Pressed {
          if let Some(w) = handle.get_window("overlay") {
            let vis = w.is_visible().unwrap_or(false);
            if vis {
              let _ = w.hide();
            } else {
              let _ = w.show();
              let _ = w.set_focus();
            }
          }
        }
      })?;

      app.global_shortcut().register(shortcut)?;
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running LocalFlow");
}