# Rico Plus Packaging

Build the Fedora 43/44 x86_64 AppImage as a normal desktop user:

```bash
./rico_plus/packaging/fedora/install-build-deps.sh
./rico_plus/packaging/fedora/build-appimage.sh
```

Artifacts:

```text
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage.sha256
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage.build-info.txt
```

Test an artifact with:

```bash
./rico_plus/packaging/fedora/test-appimage.sh \
  rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage
```

The builder runs the source release gate, creates an isolated environment,
builds the PyInstaller one-folder bundle, validates desktop/AppStream metadata,
tests the unfused AppDir, and then creates and checks the AppImage.
