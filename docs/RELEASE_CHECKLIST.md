# Pdink release checklist

Use this checklist for every public Windows release.

## Before building

- [ ] Update `CHANGELOG.md`.
- [ ] Update `MyAppVersion` in `installer/Pdink_installer.iss`.
- [ ] Confirm `GITHUB_PROJECT_URL` in `app/main.py`.
- [ ] Confirm the application starts and the icon appears in the title bar.
- [ ] Confirm the selected-language limit is one to three.
- [ ] Confirm Markdown and plain-text output.
- [ ] Confirm the last folder and selected language settings persist.

## Build and test

- [ ] Rebuild the portable folder with PyInstaller.
- [ ] Run `dist/Pdink/Pdink.exe`.
- [ ] Test PDF OCR, image OCR, DOCX, XLSX, and PPTX.
- [ ] Test at least one language other than English.
- [ ] Build `Pdink-Setup-<version>.exe` with Inno Setup.
- [ ] Install on a second Windows computer without Python or Tesseract.
- [ ] Test the desktop and Start Menu shortcuts.

## Publish

- [ ] Commit and push source changes.
- [ ] Create GitHub tag `v<version>`.
- [ ] Draft a GitHub Release with the same tag.
- [ ] Upload `Pdink-Setup-<version>.exe`.
- [ ] Add release notes from `CHANGELOG.md`.
- [ ] Publish the release.
