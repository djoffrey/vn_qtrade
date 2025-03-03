mkdir -v /var/cache/swap
cd /var/cache/swap
sudo dd if=/dev/zero of=swapfile bs=1K count=4M
sudo mkswap swapfile
sudo chmod 600 swapfile
sudo swapon swapfile
echo "/var/cache/swap/swapfile none swap sw 0 0" | tee -a /etc/fstab