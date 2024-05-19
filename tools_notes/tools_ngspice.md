Based on the instructions [here](https://deac-riga.dl.sourceforge.net/project/ngspice/ng-spice-rework/42/NGSPICE%20on%20Red%20Hat%20Like%20Distributions.pdf)

See chapter 32 of the [manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf)

# Downloading:

```shell
wget https://sourceforge.net/projects/ngspice/files/ng-spice-rework/42/ngspice-42.tar.gz
tar -xzf ngspice-42.tar.gz
cd ngspice-42
mkdir release
cd release
../configure
make
sudo make install
```

you can remove with

```
sudo make uninstall
```