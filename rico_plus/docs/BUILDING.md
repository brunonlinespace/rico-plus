# Building Rico Plus

## Source environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r rico_plus/requirements.txt
python main.py
```

## Release validation

```bash
python -m rico_plus.tools.release_check
```

The release check validates identity, static architecture, assets, RTF corpus
behavior, and the source manifest. With PyQt6 installed it also runs the Qt
round-trip and workspace integration suites.

## Fedora 43/44 AppImage

```bash
./rico_plus/packaging/fedora/install-build-deps.sh
./rico_plus/packaging/fedora/build-appimage.sh
```

Run the builder as the normal desktop user. The dependency helper invokes
`sudo dnf`; the builder itself must not run with `sudo` outside a controlled
container using `ALLOW_ROOT_BUILD=1`.

Expected output:

```text
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage.sha256
rico_plus/dist/Rico_Plus-0.0.2-x86_64.AppImage.build-info.txt
```

Validate the final artifact on the intended X11 and Wayland desktop targets.
