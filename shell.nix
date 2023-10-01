{ pkgs ? import <nixpkgs> {}
}:

pkgs.mkShell {
  buildInputs = [
    pkgs.which
    pkgs.htop
    pkgs.zlib
    pkgs.pandoc
    pkgs.ngspice # 41 (latest)
    pkgs.gtkwave # 3.3.117, from Aug 2023 (latest)
    pkgs.xyce # 7.6, from Nov 2022 (7.7 is latest)
  ];
  
# VIRTUAL_ENV_DISABLE_PROMPT=1;		# would stop the (.venv) prompt prefix, as nix already modifies this

shellHook = ''
	if [ -e .venv/bin/activate ];
		then source .venv/bin/activate;
	else
		python -m venv .venv;
		source .venv/bin/activate;
		python -m pip install --upgrade pip;
		pip install -r requirements.txt;
	fi

export PS1="\[\033[1;32m\][nix-shell:\w]\$\[\033[0m\] "	# removes (.venv) and leading spice on nix prompt

'';

LOCALE_ARCHIVE="/usr/lib/locale/locale-archive";  # let's nix read the LOCALE, to silence warning messages

}
