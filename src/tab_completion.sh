#!/bin/bash
# Bash completion for frida makefile

_frida_make_completion() {
    local cur prev words cword
    _init_completion || return

    # Get the make target (first non-option argument)
    local target=""
    local i
    for ((i=1; i < cword; i++)); do
        if [[ ${words[i]} != -* ]] && [[ ${words[i]} != make ]]; then
            target=${words[i]}
            break
        fi
    done

    # Complete make targets
    local targets="setup all gds lef netlist clean_netlist sim clean_sim view strmout lefout cdlout pvsdrc viewdrc behavioral ngspice help"

    # If no target yet, complete with targets
    if [[ -z "$target" ]]; then
        COMPREPLY=($(compgen -W "$targets" -- "$cur"))
        return 0
    fi

    # For targets that need a component name
    case "$target" in
        gds|lef|view|viewdrc)
            # Complete with Python files in src/ (without .py extension)
            if [[ -d src ]]; then
                local files=(src/*.py)
                local basenames=()
                for f in "${files[@]}"; do
                    if [[ -f "$f" ]]; then
                        basenames+=("$(basename "$f" .py)")
                    fi
                done
                COMPREPLY=($(compgen -W "${basenames[*]}" -- "$cur"))
            fi
            ;;

        netlist|clean_netlist|sim|clean_sim)
            # Complete with component names from spice/*.sp files
            if [[ -d spice ]]; then
                local comps=()
                for f in spice/*.sp; do
                    if [[ -f "$f" ]] && [[ "$(basename "$f")" != tb_* ]]; then
                        comps+=("$(basename "$f" .sp)")
                    fi
                done
                COMPREPLY=($(compgen -W "${comps[*]}" -- "$cur"))
            fi

            # Also complete tech= and workers= parameters
            if [[ "$cur" == tech=* ]]; then
                # Extract technologies from generate_netlists.toml
                if [[ -f spice/generate_netlists.toml ]]; then
                    local techs=$(grep '^\[' spice/generate_netlists.toml | grep -v '\.' | sed 's/\[//g;s/\]//g' | tr '\n' ' ')
                    local prefix="${cur%%=*}="
                    local suffix="${cur#*=}"
                    COMPREPLY=($(compgen -P "$prefix" -W "$techs" -- "$suffix"))
                fi
            elif [[ "$cur" == workers=* ]]; then
                # Suggest some common worker counts
                local prefix="${cur%%=*}="
                local suffix="${cur#*=}"
                COMPREPLY=($(compgen -P "$prefix" -W "1 2 4 8 16 32" -- "$suffix"))
            elif [[ "$cur" != *=* ]]; then
                # Suggest parameter names
                COMPREPLY=($(compgen -W "tech= workers=" -- "$cur"))
            fi
            ;;

        behavioral)
            # Complete with run scripts in src/runs/
            if [[ -d src/runs ]]; then
                local runs=()
                for f in src/runs/*.py; do
                    if [[ -f "$f" ]]; then
                        runs+=("$(basename "$f" .py)")
                    fi
                done
                COMPREPLY=($(compgen -W "${runs[*]}" -- "$cur"))
            fi
            ;;

        ngspice)
            # Complete with testbench files
            if [[ -d spice ]]; then
                local tbs=()
                for f in spice/tb_*.sp; do
                    if [[ -f "$f" ]]; then
                        tbs+=("$(basename "$f" .sp)")
                    fi
                done
                COMPREPLY=($(compgen -W "${tbs[*]}" -- "$cur"))
            fi
            ;;
    esac

    return 0
}

# Register the completion function
complete -F _frida_make_completion make
