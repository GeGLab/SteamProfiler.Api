# SteamProfiler identity

`steamprofiler.png` is an unchanged copy of `site/icon-512.png` in
SteamProfiler.Front. `steamprofiler.svg` is the original `site/favicon.svg`.
The mark represents the site's library treemap.

The comparison renderer uses the palette from `site/style.css`: background
`#0b0a0e`, panel `#131219`, secondary panel `#1a1822`, line `#282631`, text
`#eeecf3`, muted text `#8e8a9b` and accent `#ffb454`. The other profile uses
the neutral text colour to distinguish its data without adding another accent.

Bricolage Grotesque, Archivo and IBM Plex Mono were converted from the
frontend's existing WOFF2 files to TTF for Pillow. Their OFL licenses are in
`../fonts/`. Conversion is a development step; no font conversion package is
needed by the service.
