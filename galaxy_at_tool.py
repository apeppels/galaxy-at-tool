"""
Script used to expose and issue AT commands on the Samsung G950F and G965F.
by Alwin Peppels
"""
import os
import sys
import usb.core
import serial
from time import sleep

DEBUG = False

SERIAL_PORT = "/dev/ttyACM0"
GALAXY_ID_VENDOR = 0x04e8
GALAXY_ID_PRODUCT = 0x6860

"""Identifiers for USIM EFs in hex, along with the names 
and locations of the fields returned in 1-indexed bytes.
This matches how they are noted in the ETSI USIM specification """
EF_DICT = {
    "IMSI": [
        0x6f07,
        {
            "length":[1,1],
            "IMSI":[2,9]
        }
    ],
    "GSM Ciphering key Kc": [
        0x6f20,
        {
            "Kc":[1,8],
            "sequence number": [9,9]
        }
    ],
    "Ciphering and Integrity keys":[
        0x6f08, 
        {
            "KSI":[1,1], 
            "CK":[2,17],
            "IK":[18,33]
        }
    ],
    "Ciphering and Integrity Keys for Packet Switched domain": [
        0x6f09,
        {
            "KSIPS":[1,1],
            "CKPS": [2,17],
            "IKPS": [18, 33]
        }
        
    ],
    "TMSI, LAI, RFU and Location update status":[
        0x6f7e,
        {
            "TMSI":[1,4],
            "LAI": [5,9],
            "RFU": [10,10],
            "LUS": [11,11]
        }
    ],
    "KcGPRS":[
        0x6f52,
            {
            "KcGPRS":[1,8],
            "sequence number": [9,9]
            }        
    ],
    "PTMSI, PTMSI Signature Value, RAI and RAUS":[
        0x6f73,
        {
            "PTMSI":[1,4], 
            "PTMSI signature":[5,7],
            "Routing Area Information":[8,13],
            "Routing Area Update Status":[14,14],
        }
    ]
}

DOWNLOAD_MODE = "+FUS?"

# Read template for the restricted SIM Access AT command to query EFs
RSM_TEMPLATE = "+CRSM=176,{},0,0,0"

# AT command to read up to 250 values out of the SIM phone book
PB_READ = "+CPBR=1,250"

# Vendor-specific AT command to retrieve Android device info
DEVINFO = "+DEVCONINFO"

# AT command to return error descriptions instead of codes
VERBOSE_ERROR = "+CMEE=2"

# AT command to change the SMS Center number
GET_SMSC = "+CSCA?"
SET_SMSC = "+CSCA=\"telephone number\""

# AT command to request IMSI
GET_IMSI = "+CIMI?"

"""AT command to set unconditional forwarding
digit 1 : 0=unconditional, 1=busy, 4=all
digit 2 : 2=read, 3=set, 4=erase"""
GET_FWD_CONF = "+CCFC=4,2"
FORWARD_UNCONDITIONAL = "+CCFC=0,3,\"telephone number\""

dots = 0
def wait_print(text):
    global dots
    i = dots % 4
    sys.stdout.write("\r{}{}{}".format(text, "." * i, " " * (5 - i)))
    sys.stdout.flush()
    dots += 1
    sleep(0.5)


def wait_usb(id_vendor, id_product):
    dev = None
    while dev == None:
        dev = usb.core.find(idVendor=id_vendor, idProduct=id_product)
        wait_print(
            "Waiting for idVendor:{} and idProduct:{}".format(
                hex(id_vendor), 
                hex(id_product)
            )
        )
    print("\t\tdevice connected.")
    return dev


def get_usb_conf(usb_device):
    return usb_device.get_active_configuration().bConfigurationValue


def switch_usb_config(usb_device):
    active_config = get_usb_conf(usb_device)
    if active_config == 2:
        print "Configuration 0x2 already active, skipping reset"
    else:
        for _ in range(10):
            try:
                usb_device.reset()
                usb_device.reset()
                usb_device.set_configuration(0x2)
                active_config = get_usb_conf(usb_device)
                if active_config == 2:
                    print "\t\tswitched successfully."
                    break
            except Exception as e:
                pass
            wait_print("Resetting USB and switching to configuration 0x2")


def wait_serial_port(port):
    found = False
    for _ in range(15):
        wait_print("Checking if {} is available".format(port))
        if os.path.exists(port):
            print "\t\t\tsuccess."
            break


def write_at_cmd(port, cmd, maxlines=5, timeout=0.5):
    at_cmdline = "AT{}\r\n".format(cmd)
    if DEBUG:
        print "\n", at_cmdline.strip()
    with serial.Serial(port, timeout=timeout) as usbserial:
        usbserial.write(at_cmdline)
        res = ""
        # Read a max of maxlines from input
        for _ in range(maxlines):
            try:
                res += usbserial.readline()
                if "OK" in recv or "ERROR" in recv:
                    break
            except Exception as e:
                pass
        if DEBUG:
            print res
        return res.strip()

def strip_cmd(text):
    """For parsing, we don't need the command echoed back.
    You can disable this with ATE0 but it's a handy check to prevent
    mixing up the response to the command with other output.
    Restore any colons in the data that we also might split on."""
    return ":".join(text.split(":")[1:])


def wait_at_cmd(port):
    """Send the basic "AT" command until the port responds with "OK"
    Return false if there is an error sending anything."""
    res = ""
    err = 0
    while "OK" not in res:
        wait_print("Pinging AT cmd, wait 30s and unlock phone to proceed")
        try:
            res = write_at_cmd(port, "", maxlines=5, timeout=1.)
        except Exception as e:
            err += 1
            if DEBUG:
                print e
            sleep(1)
            # If tty drops too often during this stage, we need to reset the USB
            if err >= 9:
                print "ERROR: connection to serial device lost, resetting USB"
                return False
    print "\tAT returned OK"
    return True


def send_crsm(port, field):
    res = ""
    while "+CRSM" not in res:
        res = write_at_cmd(port, RSM_TEMPLATE.format(field), timeout = 0.1)
    # Get the response line that contains our extended AT command
    return [line for line in res.split("\n") if "+CRSM" in line][0]


def wait_switch_usb(port, id_vendor, id_product): 
    if not os.path.exists(port):
        dev = wait_usb(id_vendor, id_product)
        switch_usb_config(dev)
        wait_serial_port(port)
    else:
        print "Serial device already present, skipping USB config switch"


def dump_phonebook():
    pb_str = write_at_cmd(SERIAL_PORT, PB_READ, maxlines=250, timeout=2)
    formatted = ""
    for line in pb_str.split("\n"):
        if not line.strip() or not "+CPBR" in line:
            continue
        # phonebook entry fields
        f = strip_cmd(line).split(",")
        # remove quotes arounds responses
        f = [s.replace('"','') for s in f]
        numtype = int(f[2])
        if numtype == 129:
            numtype = "Natnl."
        if numtype == 145:
            numtype = "Intl."
        if numtype == 0:
            numtype = "Null."
        # pad dem bad bois with some whitespace to fix the tabs going haywire
        phonenum = f[1]+" "*(15-len(f[1]))
        numtype = numtype+" "*(5-len(str(numtype)))
        # add formatted line to final output
        formatted += "Index:{}\tNumber:{}\tType:{}\tName:{}\n".format(
                f[0], phonenum, numtype,f[3]
            )
    return formatted


def dump_devconinfo():
    """Vendor-specific command. Unline the rest, it gets returned 
    in the format of KEY(VALUE);KEY(VALUE)"""
    formatted = ""
    devconinfo = write_at_cmd(SERIAL_PORT, DEVINFO,timeout=8)
    devconinfo = strip_cmd(devconinfo)
    devconinfo = devconinfo.split(";")
    for i in devconinfo:
        if not len(i.strip()):
            continue
        i = i.split("(")
        # First field can contain some whitespace
        name = i[0].strip()
        # The end contains an #OK# after a newline
        val =  i[1].replace(")","").split("\n")[0]
        formatted += "\n{}\t\t{}".format(name, val)
    return formatted


def dump_iccid():
    formatted = ""
    chunks = []
    name = "ICCID"
    iccid = send_crsm(SERIAL_PORT, 0x2fe2).split('"')[1]
    for i in range(0, len(iccid), 2):
        chunks.append(iccid[i:i+2])
    formatted += "{}{}\t{}\n".format(name," "*(30 -len(name)), " ".join(chunks))
    formatted += "{}".format(" ".join([chunk[::-1] for chunk in chunks]))
    return formatted


def dump_network_info():
    # Dumping USIM files with the CRSM command
    formatted = ""
    for file_name,ident in EF_DICT.iteritems():
        formatted += "Dumping {}\n".format(file_name)
        # get return value from between quotes
        res = send_crsm(SERIAL_PORT,ident[0]).split('"')[1]
        # get our offsets
        split = ident[1]
        for name, offsets in split.iteritems():
            # some extra "tabbing"
            formatted += "{} {}\t".format(name, " "*(30 -len(name)))
            # -1 to translate ETSI spec offsets to 0-index
            octets = []
            for byte in range(offsets[0]-1,offsets[1]):
                # *2 because each bytes takes up 2 characters
                octets.append(res[byte*2:(byte+1)*2])
            formatted += " ".join(octets)
            if name  == "IMSI":
                formatted += '\n'
                formatted += " ".join([
                    octets[0][1], 
                    octets[0][0] + octets[1][::-1], 
                    octets[2][::-1]]
                )
                formatted += ''.join([o[::-1] for o in octets[3:]])
            if name == "LAI":
                formatted += '\n'
                formatted += " ".join([
                    octets[0][::-1] + octets[1][1], 
                    octets[2][::-1] + octets[1][0], 
                    octets[3][::-1] + octets[4][::-1]
                ])
            formatted += '\n'
        formatted += '\n'
    return formatted


def main():
    """Sometimes the USB connection resets after switching, loop to retry
    until we are sure we can send AT commands"""
    serial_present = False
    while not serial_present:
        wait_switch_usb(SERIAL_PORT, GALAXY_ID_VENDOR, GALAXY_ID_PRODUCT)
        serial_present = wait_at_cmd(SERIAL_PORT)
        if serial_present:
            break
        sleep(3)
    
    print "\n##SUCCESS##"

    # Set error mode to text
    write_at_cmd(SERIAL_PORT, VERBOSE_ERROR, timeout=0.1)
    if len(sys.argv) > 1 and sys.argv[1] == '--shell':
        while True:
            cmd = raw_input()
            print write_at_cmd(SERIAL_PORT, cmd)
    print "\n\nDumping SIM info\n"
    print dump_network_info() 
    
    # Incidentally there's a double newline the end of the previous function
    print "Dumping ICCID"
    print dump_iccid()

    print "\n\nDumping device info"
    print dump_devconinfo()

    print "\n\nDumping SIM phonebook"
    print dump_phonebook()

if __name__ == "__main__":
    main()

