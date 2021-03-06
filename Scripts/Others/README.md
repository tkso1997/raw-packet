# Miscellaneous scripts

## Script: [network_conflict_creator.py](https://github.com/raw-packet/raw-packet/blob/master/Scripts/Others/network_conflict_creator.py)

Script for creating network conflicts for varius testing.

```
root@kali:~/raw-packet# python3 Scripts/Others/network_conflict_creator.py --help
usage: network_conflict_creator.py [-h] [-i INTERFACE] [-t TARGET_IP]
                                   [-m TARGET_MAC] [--replies] [--requests]
                                   [--broadcast] [-p PACKETS] [-q] [-e]

Network conflict creator script

optional arguments:
  -h, --help            show this help message and exit
  -i INTERFACE, --interface INTERFACE
                        Set interface name for listen and send packets
  -t TARGET_IP, --target_ip TARGET_IP
                        Set target IP address
  -m TARGET_MAC, --target_mac TARGET_MAC
                        Set target MAC address
  --replies             Send only ARP replies
  --requests            Send only ARP requests
  --broadcast           Send broadcast ARP requests
  -p PACKETS, --packets PACKETS
                        Number of ARP packets (default: 10)
  -q, --quiet           Minimal output
  -e, --exit            Exit on success
```

### Sample script output:
![network_conflict_creator.py output](https://raw-packet.github.io/static/images/screenshots/network_conflict_creator.py_screenshot.png)

### Traffic sample generated by this script:
![network_conflict_creator.py traffic](https://raw-packet.github.io/static/images/screenshots/network_conflict_creator.py_traffic.png)

---

## Script: [sniff_test.py](https://github.com/raw-packet/raw-packet/blob/master/Scripts/Others/sniff_test.py)

**Under Construction**

---

## Script: [time_test.py](https://github.com/raw-packet/raw-packet/blob/master/Scripts/Others/time_test.py)

**Under Construction**

---
