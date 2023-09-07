{ pkgs ? import <nixpkgs> {}
}:

pkgs.mkShell {
  buildInputs = [
    pkgs.which
    pkgs.htop
    pkgs.zlib
    pkgs.ngspice # 41 (latest)
    pkgs.xyce # 7.6, from Nov 2022 (7.7 is latest)
  ];


  shellHook = ''
    if [ -e .venv/bin/activate ]; then source .venv/bin/activate; fi
  '';
  LOCALE_ARCHIVE="/usr/lib/locale/locale-archive";  # let's nix read the LOCALE, to silence warning messages
}
