from configparser import ConfigParser
import re
import sys
import time
import select
import socket

"""
Authors: Quin Burrell and Alex McCarty
Date:    21 March 2021
Purpose: Parses router.ini files and does basic error checks
TODO:
split horizon poisoned reverse
time outs
error catching
"""


class RipEntry:
    """An object that represents all the information about the router for an RIP Entry"""

    def __init__(self, router_id, metric, next_hop, timer):
        self.router_id = router_id
        self.metric = metric
        self.next_hop = next_hop
        self.timer = timer

    def build_packet(self):
        return ([0] * 7) + [self.router_id] + ([0] * 11) + [self.metric]


def error_msg(error_code):
    """Returns an error message associated with the number error_code"""
    error_text = {
        0: "Please enter a value between 1 and 64000",
        1: "Your input ports do not match your output ports. Please update your configuration file",
        2: "Please make sure you do not have the same entry in your input and output port fields",
        3: "Please make sure your port numbers are between 1024 and 64000",
        4: "Failed to initialise sockets",
        10: "Packet contains less than one RIP Entry",
        11: "RIP Packet header incorrect",
        12: "Packet contains fragments",
        13: "Given metric is out of range",
        20: "An error on the socket"
    }
    return error_text[error_code]


def read_config(file):
    """reads a .ini file intended as a config file for a router. If the .ini file has the expected format and
    information an RIP entry is created with the router id, and lists of the input and output port numbers."""
    config = ConfigParser()  # Creates an instance of the config parser
    config.read(file)  # Config parser reads the given router file

    # Router ID
    router_num = int(config['router']['router_id'])  # Extracts router id from config file
    if 1 >= router_num >= 64000:  # Checks id is a valid id
        sys.exit(error_msg(0))  # Error

    # Input ports
    inputs = config['router']['input_ports'].split(', ')  # Extracts input ports from config file
    input_ports = []
    neighbours = []

    for entry in inputs:
        entry = int(entry)
        if 1024 < entry < 64000:  # Checks input port is valid
            input_ports.append(entry)  # If valid, appends to list fo input ports
            neighbours.append(
                int((entry - (router_num * 1000)) / 100))  # Finds the router id of the neighbouring router
        else:

            sys.exit(error_msg(0))  # Error

    # Outputs
    out = config['router']['outputs'].split(', ')  # Extracts outputs from the config file
    output_ports = []
    rip_entries = []  # A list of RipEntry obj, one for each router that this router is aware of
    rip_entries.append(RipEntry(router_num, 0, router_num, time.time()))

    for entry in out:
        re_result = re.search("(.*)-(.)-(.)", entry).groups()  # Uses a regex to split the values of the entry
        output_port, metric, router_id = [int(i) for i in re_result]  # Changes all values to ints
        if 1024 <= output_port <= 64000:  # Checks port number is valid
            if output_port not in input_ports:  # Checks this port number is not also an input port
                if router_id in neighbours:  # Checks that the output port has a matching input port for that router
                    output_ports.append((router_id, output_port))
                    rip_entries.append(RipEntry(router_id, metric, router_id, time.time()))
                else:
                    sys.exit(error_msg(1))  # Error
            else:
                sys.exit(error_msg(2))  # Error
        else:
            sys.exit(error_msg(3))  # Error

    sockets = init_sockets(input_ports)  # A list of sockets that this router is neighbouring
    return sockets, output_ports, rip_entries


def rip_packet(rip_entries, receiver):
    """taking a list of the entries in an rip table, builds a byte array to send as a packet"""
    packet = [2, 2, 0, 0]  # The RIP header
    for entry in rip_entries:
        real_metric = entry.metric
        if entry.next_hop == receiver:
            entry.metric = 16
        packet += entry.build_packet()  # a bytearray representing each RIP Entry
        entry.metric = real_metric
    byte_packet = bytearray(packet)
    return byte_packet  # returns the entire packet as a bytearray


def init_sockets(inputs):
    sockets = []  # a list of the input sockets available
    try:
        for i in range(len(inputs)):
            sockets += [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]  # opens a sockets for each supplied input
        for i, sock in enumerate(sockets):
            sock.bind(('localhost', inputs[i]))
            print("socket on port " + str(inputs[i]) + " initialised")
    except socket.error:
        sys.exit(error_msg(4))  # Error. Socket could not be bound.
    return sockets


def format_check(rec_packet):
    """Returns True if the received packet is formatted correctly, otherwise provides an error message and False"""
    if len(rec_packet) < 4:  # packet contains at least one RIP entry
        print(error_msg(10))
    elif rec_packet[0:4] != b'\2\2\0\0':  # Packet header is correct
        print(error_msg(11))
    elif (len(rec_packet) - 4) % 20 != 0:
        print(error_msg(12))
    else:
        return True
    return False


def update_table(rec_packet, routing_table, index=24):
    """updates routing table to be in accordance with the received packet"""
    sender = rec_packet[11]
    current_routers = []
    for entry in routing_table:
        if entry.router_id != routing_table[0].router_id:
            current_routers += [entry.router_id]
        if entry.router_id == sender:
            entry.timer = time.time()
            if entry.metric == 16:
                while index < len(rec_packet):
                    if rec_packet[index+7] == routing_table[0].router_id:
                        entry.metric = rec_packet[index+19]
                        entry.timer = time.time()
                        break
                    index += 20
                print('contact', entry.router_id, entry.metric)
            metric_to_sender = entry.metric

    index = 24
    while index < len(rec_packet):
        id = rec_packet[index+7]
        metric = rec_packet[index+19] + metric_to_sender
        if id in current_routers:
            for entry in routing_table:
                if entry.router_id == id:
                    if metric >= 16 and entry.next_hop == sender:
                        entry.metric = 16
                        entry.timer = 0
                    else:
                        entry.timer = time.time()
                        if entry.metric > metric:
                            entry.metric = metric
                            entry.next_hop = sender
        else:
            routing_table.append(RipEntry(id, metric, sender, time.time()))
        index += 20

    return routing_table


def timeout_check(routing_table):
    """Checks the routing table for timeouts and if one is found, metric to that router is set to unreachable"""
    for entry in routing_table:
        if entry.timer != 0 and entry.timer < time.time() - 30:
            print("timeout on router", entry.router_id)
            entry.metric = 16
            entry.timer = 0
    return routing_table


def print_routing_table(routing_table):
    """prints the current state of the routing table"""
    for entry in routing_table:
        print(entry.build_packet())


def mainloop():
    """mainloop of the program"""
    filename = sys.argv[1]  # Holds the variable given in the command line
    sockets, outputs, routing_table = read_config(filename)  # Produces these variable from the given file
    output_socks = []
    # The router informs its neighbours of its own existence
    for i, output in enumerate(outputs):
        output_socks += [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]
        output_socks[i].sendto(rip_packet(routing_table, output[0]), ('localhost', output[1]))

    while 1:
        if routing_table[0].timer < time.time() - 10:  # router checks its own timer for timeout
            routing_table[0].timer = time.time()
            print("Periodic Update")
            print_routing_table(routing_table)
            for i, sock in enumerate(output_socks):
                sock.sendto(rip_packet(routing_table, outputs[i][0]), ('localhost', outputs[i][1]))

        routing_table = timeout_check(routing_table)
        try:
            # The router then waits for updates
            readable, _, _ = select.select(sockets, [], [], 1)
            for read in readable:  # For each socket within the list of sockets
                data, sender_addr = read.recvfrom(1024)
                data = bytearray(data)

                # Router checks the new packet format and if it is different from current routing table
                if format_check(data):
                    print("packet received from router", data[11], str(sender_addr))
                    routing_table = update_table(data, routing_table)

        except socket.error():
            error_msg(20)


mainloop()
