# galaxy-at-tool
Tool to expose the AT modem om Samsung Galaxy devices and interact with it.
It works over USB connections in MTP mode with factory settings.

# Requirements
This script depends on `libusb` and `pyserial`, these can be installed with:

`pip install pyusb pyserial`

# Usage:
`python galaxy_at_tool.py`

By default, the script dumps the following information
* Network identity
  * IMSI, TMSI, PTMSI, LAI, RAI, ICCID
* Keys
  * Kc, KcGPRS, CK, IK, CKPS, IKPS
* Device info
  * Model, IMEI, SN, Software Versions (`AT+DEVCONINFO`)
* SIM Phonebook

Included but not used are commands to:
* Write entries to the SIM Phonebook.
* Configure unconditional call forwarding.
* Place the device in Download Mode (`AT+FUN?`).
* Set the SMS center number.

A `--shell` option can be supplied to interactively enter commands (these are prefixed with `AT`, e.g., entering `E0` disables echoing by sending `ATE0`)  . 


# Background Information
CVE-2016-4030 noted that the GT-I9192 (Galaxy S4) exposes a secondary USB configuration in MTP mode that provides direct access to the AT modem. This appears to still work this way on both the G950F and G965F (S8 and S9), provided that they are unlocked.

The phone presents with two possible USB configurations when connecting, as can be 
read from the bNumConfigurations value in the output of 'lsusb -v'.
If USB debugging is enabled, the communication device is exposed by the default 
USB configuration. For current Galaxy phones, it can be found at /dev/ttyACM0.

The following is a Python implementation of finding a Galaxy phone and switching to this configuration:

```
import usb.core
dev = usb.core.find(idVendor=0x04e8, idProduct=0x6860) 
dev.reset()
dev.set_configuration(0x2)
```

In my experience this switching might take a retry or two.
After this, /dev/ttyACM0 is reachable.

This enables issuing AT commands: 

`echo -e "AT \r\n" >/dev/ttyACM0`    

NB:
In Ubuntu, the phone is auto-mounted, it must first be unmounted.
The device only accepts AT commands when the keyguard (lockscreen) is inactive.

Samsung's stance is that because the AT commands can only be issued when the phone is unlocked, there is sufficient protection from abuse, therefore it is Working as Intended. However they will "..continue to make an effort to improve the security of Samsung Mobile products and minimize risk to our end-consumers.". 

I personally see risk because users are generally not aware of the security implication of unlocking their phone while charging from an untrusted source. An option to conveniently disable access to AT commands when one is aware of the risk is also lacking.

Resources:

https://atcommands.org/

https://www.etsi.org/deliver/etsi_ts/131100_131199/131102/04.15.00_60/ts_131102v041500p.pdf
