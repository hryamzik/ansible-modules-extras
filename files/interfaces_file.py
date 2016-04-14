#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# (c) 2016, Roman Belyakovsky <ihryamzik () gmail.com>
#

DOCUMENTATION = '''
---
module: interfaces_file
short_description: Tweak settings in /etc/network/interfaces files
extends_documentation_fragment: files
description:
     - Manage (add, remove, change) individual interface options in an interfaces-style file without having
       to manage the file as a whole with, say, M(template) or M(assemble). Interface has to be presented in a file.
     - Read information about interfaces from interfaces-styled files
options:
  dest:
    description:
      - Path to the interfaces file
    required: false
    default: /etc/network/interfaces
  iface:
    description:
      - Name of the interface, required for value changes or option remove
    required: false
    default: null
  option:
    description:
      - Name of the option, required for value changes or option remove
    required: false
    default: null
  value:
    description:
      - Value of option, required for value changes
    required: false
    default: null
  backup:
    description:
      - Create a backup file including the timestamp information so you can get
        the original file back if you somehow clobbered it incorrectly.
    required: false
    default: "no"
    choices: [ "yes", "no" ]
  state:
    description:
      - If set to C(absent) the option or section will be removed if present instead of created.
    required: false
    default: "present"
    choices: [ "present", "absent" ]

notes:
   - If option is defined multiple times last one will be updated but all will be deleted in case of an absent state
   - '"pre-up", "up", "down" and "post-up" options are not currently handled properly and will be treated as mentioned earlier'
requirements: []
author: "Roman Belyakovsky (@hryamzik)"
'''

EXAMPLES = '''
# Set eth1 mtu configuration value to 8000
- interfaces_file:
    dest: /etc/network/interfaces.d/eth1.cfg
    iface: eth1
    option: mtu
    value: 8000
    backup: yes
    state: present
  register: eth1_cfg
'''

import os
import tempfile

def lineDict(line):
    return {'line': line, 'line_type':'unknown'}

def optionDict(line, iface, option, value):
    return {'line': line, 'iface': iface, 'option': option, 'value': value, 'line_type':'option' }

def read_interfaces_file(module, filename):
    f = open(filename, 'r')
    return read_interfaces_lines(module, f)

def read_interfaces_lines(module, line_strings):
    lines = []
    ifaces = {}
    currently_processing = None;
    i = 0
    for line in line_strings:
        i += 1
        words = line.split()
        if len(words) < 1:
            lines.append(lineDict(line))
            continue
        if words[0][0] == "#":
            lines.append(lineDict(line))
            continue
        if words[0] == "mapping":
            # currmap = calloc(1, sizeof *currmap);
            lines.append(lineDict(line))
            currently_processing = "MAPPING"
        elif words[0] == "source":
            lines.append(lineDict(line))
            currently_processing = "NONE"
        elif words[0] == "source-dir":
            lines.append(lineDict(line))
            currently_processing = "NONE"
        elif words[0] == "iface":
            currif = {}
            iface_name, address_family_name, method_name =  words[1:4]
            if len(words) != 4:
                module.fail_json(msg="Incorrect number of parameters (%d) in line %d, must be exectly 3" % (len(words), i))
                # TODO: put line and count parameters
                return None, None;
            
            currif['name']           = iface_name
            currif['address_family'] = address_family_name
            currif['method']         = method_name
            
            ifaces[iface_name]   = currif
            lines.append({'line':line, 'iface':iface_name, 'line_type':'iface', 'params': currif})
            currently_processing     = "IFACE"
        elif words[0] == "auto":
            lines.append(lineDict(line))
            currently_processing = "NONE"
        elif words[0] == "allow-":
            lines.append(lineDict(line))
            currently_processing = "NONE"
        elif words[0] == "no-auto-down":
            lines.append(lineDict(line))
            currently_processing = "NONE"
        elif words[0] == "no-scripts":
            lines.append(lineDict(line))
            currently_processing = "NONE"
        else:
            if currently_processing == "IFACE":
                option_name = words[0]
                # TODO: if option_name not in ["pre-up", "up","down","post-up"]:
                # TODO: if option_name in currif.options
                value = " ".join(words[1:])
                lines.append(optionDict(line,currif['name'],option_name, value))
                currif[option_name] = value
            elif currently_processing == "MAPPING":
                lines.append(lineDict(line))
            elif currently_processing == "NONE":
                lines.append(lineDict(line))
            else:
                module.fail_json(msg="misplaced option %s in line %d" % (line, i))
                return None, None
    return lines, ifaces

def setInterfaceOption(module, lines, iface, option, raw_value, state):
    # TODO: implement state
    value=str(raw_value)
    changed = False
    
    iface_lines = [item for item in lines if "iface" in item and item["iface"] == iface]
    
    if len (iface_lines) < 1:
        # interface not found
        module.fail_json(msg="Error: interface %s not found" % iface )
        return changed
    
    iface_options = filter(lambda i: i['line_type'] == 'option', iface_lines)
    target_options = filter(lambda i: i['option'] == option, iface_options)
    
    if state == "present":
        if len (target_options) < 1:
            changed = True
            # add new option
            last_line_dict = iface_lines[-1]
            last_line = last_line_dict['line']
            prefix_start = last_line.find(last_line.split()[0])
            suffix_start = last_line.find(last_line.split()[-1]) + len(last_line.split()[-1])
            line = last_line[:prefix_start]
        
            if len (iface_options) < 1:
                # interface has no options, ident
                line += "    "
            line += "%s %s" % (option, value)
            line += last_line[suffix_start:]
            option_dict = optionDict(line, iface, option, value)
            index = len(lines) - lines[::-1].index(last_line_dict)
            lines.insert(index, option_dict)
        else:
            # if more than one option found edit the last one
            if cmp(target_options[-1]['value'].split(), value.split()) != 0:
                changed = True
                target_option = target_options[-1]
                old_line = target_option['line']
                old_value = target_option['value']
                prefix_start = old_line.find(option)
                start = old_line.find(old_value, prefix_start + len(option) - 1 )
                line = old_line[:start]+old_line[start:start+len(old_value)].replace(old_value,value)+old_line[start+len(old_value):]
                index = len(lines) - lines[::-1].index(target_option) - 1
                lines[index] = optionDict(line, iface, option, value)
    elif state == "absent":
        if len (target_options) >= 1:
            changed = True
            lines = filter(lambda l: l != target_options[0], lines)
    else:
        module.fail_json(msg="Error: unsupported state %s, has to be ither present or absent" % state)
    
    return changed, lines
    pass

def write_changes(module,lines,dest):

    tmpfd, tmpfile = tempfile.mkstemp()
    f = os.fdopen(tmpfd,'wb')
    f.writelines(lines)
    f.close()
    module.atomic_move(tmpfile, os.path.realpath(dest))

def main():
    module = AnsibleModule(
        argument_spec = dict(
            dest      = dict(default='/etc/network/interfaces',required=False),
            iface = dict(required=False),
            option    = dict(required=False),
            value     = dict(required=False),
            backup    = dict(default='no', type='bool'),
            state     = dict(default='present', choices=['present', 'absent']),
        ),
        add_file_common_args = True,
        supports_check_mode = True
    )
    
    dest = os.path.expanduser(module.params['dest'])

    iface = module.params['iface']
    option    = module.params['option'   ]
    value     = module.params['value'    ]
    backup    = module.params['backup'   ]
    state     = module.params['state'    ]
    
    if option != None and iface == None:
        module.fail_json(msg="Inteface must be set if option is defined")
    
    if option != None and state == "present" and value == None:
        module.fail_json(msg="Value must be set if option is defined and state is 'present'")
    
    lines, ifaces = read_interfaces_file(module, dest)
    
    changed = False
    
    if option != None:
        changed, lines = setInterfaceOption(module, lines, iface, option, value, state)

    if changed:
        _, ifaces = read_interfaces_lines(module, [d['line'] for d in lines if 'line' in d])

    if changed and not module.check_mode:
        if backup:
            module.backup_local(dest)
        write_changes(module, [d['line'] for d in lines if 'line' in d], dest)
    
    
    module.exit_json(dest=dest, changed=changed, ifaces=ifaces)

from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
