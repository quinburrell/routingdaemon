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
"""


def error_msg(error_code):
    """Returns an error message associated with the number error_code"""
    error_text = {
        0: "Please enter a value between 1 and 64000",
        1: "Your input ports do not match your output ports. Please update your configuration file",
        2: "Please make sure you do not have the same entry in your input and output port fields",
        3: "Please make sure your port numbers are between 1024 and 64000",
        4: "Failed to initialise sockets"
    }
    return error_text[error_code]


def read_config(file):
    """reads a .ini file intended as a config file for a router. If the .ini file has the expected format and
    information this function creates a dictionary with the router id, and lists of the input and ouput port numbers."""
    config = ConfigParser()  # Creates an instance of the config parser
    config.read(file)  # Config parser reads the given router file

    # Create an empty dictionary which will hold info about the router
    router_dict = {}

    # Router ID
    router_num = int(config['router']['router_id'])  # Extracts router id from config file
    if 1 <= router_num <= 64000:  # Checks id is a valid id
        router_dict['router-id'] = router_num  # If valid then gets added to the router dictionary
    else:
        sys.exit(error_msg(0))  # Error

    # Input ports
    inputs = config['router']['input_ports'].split(', ')  # Extracts input ports from config file
    input_ports = []
    neighbours = []

    for entry in inputs:
        entry = int(entry)
        if 1024 < entry < 64000:  # Checks input port is valid
            input_ports.append(entry)  # If valid, appends to list fo input ports
            neighbours.append(int((entry - (router_num * 1000))/100))  # Finds the router id of the neighbouring router
        else:

            sys.exit(error_msg(0))  # Error

    router_dict['input-ports'] = input_ports  # All valid input ports are added to the router dictionary

    # Outputs
    out = config['router']['outputs'].split(', ')  # Extracts outputs from the config file
    output_ports = []

    for entry in out:
        re_result = re.search("(.*)-(.)-(.)", entry).groups()  # Uses a regex to split the values of the entry
        output_port, metric, router_id = [int(i) for i in re_result]  # Changes all values to ints
        if 1024 <= output_port <= 64000:  # Checks port number is valid
            if output_port not in router_dict['input-ports']:  # Checks this port number is not also an input port
                if router_id in neighbours:  # Checks that the output port has a matching input port for that router
                    output_ports.append([output_port, metric, router_id])
                else:
                    sys.exit(error_msg(1))  # Error
            else:
                sys.exit(error_msg(2))  # Error
        else:
            sys.exit(error_msg(3))  # Error

    router_dict['outputs'] = output_ports  # Adds all valid outputs to the router dictionary

    start = time.time()
    router_dict['timer-started'] = start  # Adds when the router turned on to the router dictionary

    print(router_dict)
    return router_dict


def construct_rip_entry(entry):
    """constructs a properly formatted list for a given rip entry"""
    entry_list = []
    return entry_list


def construct_rip_packet(req=1, rip_entries=[]):
    """taking a list of the entries in an rip table, builds a byte array to send as a packet"""
    packet_list = [req, 2, 0, 0]    # req specifies if request/response packet, plus mandatory version and 0 fields
    for entry in rip_entries:
        packet_list += construct_rip_entry(entry)
    return bytearray(packet_list)  # returns the entire packet as a bytearray


def init_sockets(inputs):
    sockets = []  # a list of the sockets available
    try:
        for i in range(len(inputs)):
            sockets += [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]  # opens a sockets for each supplied input
        for i, sock in enumerate(sockets):
            sock.bind(('localhost', inputs[i]))
            print("socket on port", inputs[i], "initialised")
    except socket.error:
        sys.exit(error_msg(4))  # Error. Socket could not be bound.
    return sockets


def mainloop():
    """mainloop of the program"""
    filename = sys.argv[1]  # Holds the variable given in the command line
    router_dict = read_config(filename)
    sockets = init_sockets(router_dict['input-ports'])
    while 1:
        # an infinite while loop starts as the router waits for packets
        readable, _, _ = select.select(sockets, [], [])
        for sock in readable:
            data, sender_addr = sock.recvfrom(1024)


mainloop()
