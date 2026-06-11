fn main() {
    if std::env::var("GAME_MACRO_ADMIN_MANIFEST").as_deref() == Ok("1") {
        let windows = tauri_build::WindowsAttributes::new()
            .app_manifest(include_str!("windows-admin.manifest"));
        let attrs = tauri_build::Attributes::new().windows_attributes(windows);
        tauri_build::try_build(attrs).expect("failed to run tauri build script");
    } else {
        tauri_build::build();
    }
}
