if [ "$(hostname -s)" = "asiclab003" ]; then
    echo "Configuring env for NFS asiclab tools"
    source /eda/local/scripts/vivado_2025.2.sh
elif [ "$(hostname -s)" = "lt177" ]; then
    echo "Configuring env for local Vivado install"
    export XILINXD_LICENSE_FILE="27506@nexus.physik.uni-bonn.de"
    source /eda/amd/2025.2/Vivado/settings64.sh
fi
