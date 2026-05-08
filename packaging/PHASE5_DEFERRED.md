# OpenLimno Studio — Phase 5 deferred work (macOS .dmg + Windows .exe)

Phase 4 (Linux AppImage) is done in this repo. Phase 5 — macOS notarized
.dmg + Windows signed .exe — requires paid developer accounts and tooling
that only the project owner can buy. This document captures everything
needed so the work can resume immediately once those resources exist.

## What's blocking

| Platform | Required | Cost (USD) | Owner action |
|----------|----------|-----------:|--------------|
| macOS    | Apple Developer Program membership | $99 / year | enrol at developer.apple.com; Team ID required for notarization |
| macOS    | Code-signing certificate (Developer ID Application) | included | downloaded via Xcode after enrollment |
| Windows  | Code-signing certificate (EV recommended for SmartScreen) | $200–500 / year | DigiCert / Sectigo / SSL.com |
| Both     | Build runners with the right OS | $0 (GitHub Actions includes macOS + Windows runners) | none |

Without these, builds will produce **unsigned** binaries that:
- macOS: Gatekeeper blocks first launch ("damaged"); user must `xattr -d com.apple.quarantine`.
- Windows: SmartScreen warns ("unrecognised app"); user clicks "More info → Run anyway".

These are operationally acceptable for an OSS project's early days, but
not for terminal users (the segment this whole Phase 4/5 push targets).

## macOS .dmg build steps (post-cert)

The PyInstaller spec already targets cross-platform; only the OS runner
and signing flow differ.

```yaml
# .github/workflows/release-macos.yml (sketch)
runs-on: macos-14   # arm64 (M-series); use macos-13 for intel
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: '3.12' }
  - run: brew install qgis pyinstaller
  - run: pyinstaller --noconfirm packaging/openlimno-studio.spec
  - name: Sign
    env:
      APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
      APPLE_CERT_P12: ${{ secrets.APPLE_CERT_P12 }}
      APPLE_CERT_PASSWORD: ${{ secrets.APPLE_CERT_PASSWORD }}
    run: |
      echo "$APPLE_CERT_P12" | base64 -d > cert.p12
      security create-keychain -p "" build.keychain
      security import cert.p12 -k build.keychain -P "$APPLE_CERT_PASSWORD"
      codesign --force --deep --options runtime \
               --sign "$APPLE_TEAM_ID" \
               dist/openlimno-studio/openlimno-studio
  - name: Build .dmg
    run: |
      brew install create-dmg
      create-dmg \
        --volname "OpenLimno Studio" \
        --window-size 600 400 \
        OpenLimnoStudio-arm64.dmg \
        dist/openlimno-studio
  - name: Notarize + staple
    env:
      APPLE_ID: ${{ secrets.APPLE_ID }}
      APPLE_APP_SPECIFIC_PASSWORD: ${{ secrets.APPLE_APP_SPECIFIC_PASSWORD }}
    run: |
      xcrun notarytool submit OpenLimnoStudio-arm64.dmg \
        --apple-id "$APPLE_ID" \
        --password "$APPLE_APP_SPECIFIC_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" \
        --wait
      xcrun stapler staple OpenLimnoStudio-arm64.dmg
```

**Manual smoke test before tagging release**:
1. Download .dmg on a non-build mac (no signing tools installed).
2. Double-click — should mount without Gatekeeper warning.
3. Drag app to /Applications.
4. Open from Launchpad — must launch in <5s without "damaged" dialog.

## Windows .exe build steps (post-cert)

```yaml
# .github/workflows/release-windows.yml (sketch)
runs-on: windows-2022
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: '3.12' }
  # OSGeo4W is the only sane way to install QGIS on Windows for embedding
  - run: |
      curl -L -o osgeo4w-setup.exe https://download.osgeo.org/osgeo4w/v2/osgeo4w-setup.exe
      ./osgeo4w-setup.exe -A -q -k -P qgis-ltr -s https://download.osgeo.org/osgeo4w/v2 -R C:\OSGeo4W
  - run: pip install pyinstaller netCDF4 pandas pyarrow shapely matplotlib
  - run: pyinstaller --noconfirm packaging/openlimno-studio-windows.spec
  - name: Sign
    env:
      WIN_CERT_P12: ${{ secrets.WIN_CERT_P12 }}
      WIN_CERT_PASSWORD: ${{ secrets.WIN_CERT_PASSWORD }}
    run: |
      echo $env:WIN_CERT_P12 | Out-File -FilePath cert.p12 -Encoding ASCII
      signtool sign /f cert.p12 /p $env:WIN_CERT_PASSWORD `
        /tr http://timestamp.digicert.com /td sha256 /fd sha256 `
        dist\openlimno-studio\openlimno-studio.exe
  - name: NSIS installer
    run: |
      choco install nsis
      makensis packaging\windows-installer.nsi
  - name: Sign installer
    run: |
      signtool sign /f cert.p12 /p $env:WIN_CERT_PASSWORD `
        OpenLimnoStudio-Setup.exe
```

You'll need a separate `openlimno-studio-windows.spec` (the binary search
paths differ on OSGeo4W: `C:\OSGeo4W\bin\qgis_*.dll` instead of
`/usr/lib/libqgis_*.so`). Reuse the rest of the current spec.

## CI matrix (full release pipeline)

```yaml
# .github/workflows/release.yml
on:
  push:
    tags: ['v*']
jobs:
  linux:    { uses: ./.github/workflows/release-linux.yml }
  macos:    { uses: ./.github/workflows/release-macos.yml }
  windows:  { uses: ./.github/workflows/release-windows.yml }
  release:
    needs: [linux, macos, windows]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            OpenLimnoStudio-x86_64.AppImage
            OpenLimnoStudio-arm64.dmg
            OpenLimnoStudio-Setup.exe
```

## Outstanding questions for the project owner

- **Apple Developer account name**: individual ($99) or organization
  ($99 + D-U-N-S verification, free DUNS but multi-week wait)? The
  organization route puts "OpenLimno" on the signature; individual puts
  your name.
- **Windows EV vs OV cert**: EV ($200-500) gives instant SmartScreen
  trust; OV ($75-150) requires building reputation over weeks of
  downloads. EV recommended for terminal-user adoption.
- **Distribution channel**: GitHub Releases (free, unbranded URL) vs
  custom website + CDN. GitHub Releases is fine for v1; consider
  homebrew (mac) and winget (windows) submissions later.

## Status checkbox

- [ ] Apple Developer Program enrolled (Team ID: ___)
- [ ] macOS Developer ID Application cert downloaded
- [ ] Windows EV code-signing cert purchased + delivered
- [ ] GitHub repo secrets populated (APPLE_*, WIN_CERT_*)
- [ ] First successful notarized macOS .dmg
- [ ] First successful signed Windows installer
- [ ] release.yml workflow merged to main
