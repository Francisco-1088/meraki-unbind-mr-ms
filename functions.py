import PySimpleGUI as sg
import time
import meraki

def gather_templates(dashboard, org_id=None):
    """
    Gathers the templates existing in the organization or organizations the API key has access to.
    If org_id is set in credentials.py file, it will only fetch the templates in that org.
    :param dashboard: Dashboard API client instance
    :param org_id: org ID if set in the credentials.py file
    """
    if org_id != None:
        orgs = [dashboard.organizations.getOrganization(org_id)]
    else:
        orgs = dashboard.organizations.getOrganizations()
    temps = []
    non_api = []
    j = 0
    for org in orgs:
        try:
            temp = dashboard.organizations.getOrganizationConfigTemplates(organizationId=org['id'])
            temps.append(temp)
            j = j + 1
        except meraki.APIError as e:
            print(e)
            temps.append(j)
            non_api.append(j)
            j = j + 1
    org_templates = []

    for i in range(len(orgs)):
        if i in non_api:
            continue
        else:
            dict = orgs[i]
            dict['templates'] = temps[i]
            org_templates.append(dict)

    for org in org_templates:
        for template in org['templates']:
            temp_nets = []
            networks = dashboard.organizations.getOrganizationNetworks(organizationId=org['id'])
            for net in networks:
                if net['isBoundToConfigTemplate'] == True:
                    if net['configTemplateId'] == template['id']:
                        temp_nets.append(net)
            template["networks"] = temp_nets

    return org_templates

def open_window(message, lines=8, width=28):
    """
    Opens a notification window when something happens during execution of the script.
    :param message: Message to include in the notification.
    :param lines: Rows reserved to the window.
    :param width: Columns reserved to the window.
    """
    layout = [
        [sg.Text(
            f'{message}',
            size=(width, lines), font=('Any', 16), text_color='#000000',
            justification='center')],
        # [sg.Image(data=imgbytes, key='_IMAGE_')],
        [sg.Exit()]
    ]
    win = sg.Window('Meraki Unbind and Retain MR/MS',
                    default_element_size=(14, 1),
                    text_justification='right',
                    auto_size_text=False,
                    font=('Helvetica', 20)).Layout(layout)
    win.Read()
    win.close()

def rollback_window(message, dashboard, src_temp_id, dst_net_id, lines=16, width=28):
    """
    Sends special notification for rolling back the changes, that is to rebind the network to its template.
    :param message: List of errors observed in execution.
    :param dashboard: Dashboard API client instance.
    :param src_temp_id: Template from which the network was unbound.
    :param dst_net_id: Unbound network.
    :param lines: Vertical space dedicated to errors.
    :param width: Horizontal space dedicated to errors.
    :return: event: choice of whether to rollback or not.
    """
    layout = [
        [sg.Text(
            'There were some errors while running the script:',
            size=(width, lines), font=('Any', 16), text_color='#ff0000',
            justification='center')],
        [sg.Text(
            f'{message}',
            size=(width, lines), font=('Any', 16), text_color='#ff0000',
            justification='center')],
        [sg.Text(
            'Would you like to roll back?',
            size=(width, lines), font=('Any', 16), text_color='#000000',
            justification='center')],
        # [sg.Image(data=imgbytes, key='_IMAGE_')],
        [sg.Button('YES'), sg.Button('NO')]
    ]
    win = sg.Window('Meraki Unbind and Retain MR/MS',
                    default_element_size=(14, 1),
                    text_justification='right',
                    auto_size_text=False,
                    font=('Helvetica', 20)).Layout(layout)
    i = True
    while i:
        event, values = win.Read()
        if event == 'YES':
            dashboard.networks.bindNetwork(networkId=dst_net_id, configTemplateId=src_temp_id, autoBind=True)
            i = False
        elif event =='NO':
            i = False

    win.close()
    return event

def user_input(message, lines=4, width=20):
    """
    Shows popup for user input
    :param message: Message to display
    :param lines: Number of lines
    :param width:
    :return:
    """
    layout = [
        [sg.Text(
            f'{message}',
            size=(width, lines), font=('Any', 16), text_color='#1c86ee',
            justification='center')],
        [sg.InputText("Input",key="_INPUT_")],
        [sg.Submit(), sg.Cancel()]
    ]
    win = sg.Window('Meraki Unbind and Retain MR/MS',
                    default_element_size=(14, 1),
                    text_justification='right',
                    auto_size_text=False,
                    font=('Helvetica', 20)).Layout(layout)
    event, values = win.Read()
    win.close()
    return event, values

def get_switch_configs(dashboard, dst_net_id):
    """
    Gets the existing switch port configs, STP configs, port schedules and access policies in the network to be unbound.
    :param dashboard: Dashboard API client instance\
    :param dst_net_id: ID of unbound network\
    :return:stp, access_policies, port_schedules, switch_port_configs
    """
    devices = dashboard.networks.getNetworkDevices(dst_net_id)
    switches = []
    for device in devices:
        if 'MS' in device['model']:
            switches.append(device)

    access_policies = dashboard.switch.getNetworkSwitchAccessPolicies(dst_net_id)
    port_schedules = dashboard.switch.getNetworkSwitchPortSchedules(dst_net_id)
    stp = dashboard.switch.getNetworkSwitchStp(dst_net_id)

    switch_port_configs = {}
    for switch in switches:
        switch_port_configs[f'{switch["serial"]}'] = dashboard.switch.getDeviceSwitchPorts(switch['serial'])
        for port in switch_port_configs[f'{switch["serial"]}']:
            for ps in port_schedules:
                if ps['id'] == port['portScheduleId']:
                    port['portScheduleId'] = ps['name']
            if 'accessPolicyNumber' in port:
                for ap in access_policies:
                    if ap['accessPolicyNumber'] == str(port['accessPolicyNumber']):
                        port['accessPolicyNumber'] = ap['name']

    return stp, access_policies, port_schedules, switch_port_configs

def get_rfprofiles(dashboard, src_temp_id, dst_net_id):
    """
    Obtains existing RF Profiles config in network to unbind and returns it to running script
    :param dashboard: Dashboard API client instance
    :param dst_net_id: ID of network to unbind
    :return: radio_settings: list of radio settings applied per AP in network to unbind
    """
    # Get existing RF Profiles in network to unbind
    rf_profiles = dashboard.wireless.getNetworkWirelessRfProfiles(networkId=src_temp_id)
    # Get devices in network
    devices = dashboard.networks.getNetworkDevices(networkId=dst_net_id)
    # Construct radio settings file for APs
    radio_settings = []
    # For every device that is an MR, get their radio settings
    for device in devices:
        if 'MR' in device['model']:
            radio_setting = dashboard.wireless.getDeviceWirelessRadioSettings(serial=device['serial'])
            for profile in rf_profiles:
                if profile['id'] == radio_setting['rfProfileId']:
                    radio_setting['profileName'] = profile['name']
            radio_settings.append(radio_setting)
    return radio_settings

def restore_rf_profiles(dashboard, src_temp_id, dst_net_id, radio_settings):
    """
    Restores RF Profiles to unbound network and applies to APs
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    """
    existing_profiles = dashboard.wireless.getNetworkWirelessRfProfiles(networkId=src_temp_id)
    for rf_profile in existing_profiles:
        upd = rf_profile
        name = rf_profile['name']
        band_selection_type = rf_profile['bandSelectionType']
        if upd['fiveGhzSettings']['minPower'] < 8:
            upd['fiveGhzSettings']['minPower'] = 8
            print('Minimum power configurable for 5GHz via API is 8')
        if upd['fiveGhzSettings']['maxPower'] > 30:
            upd['fiveGhzSettings']['maxPower'] = 30
            print('Maximum power configurable for 5GHz is 30')
        if upd['twoFourGhzSettings']['minPower'] < 5:
            upd['twoFourGhzSettings']['minPower'] = 5
            print('Minimum power configurable for 2.4GHz via API is 5')
        if upd['twoFourGhzSettings']['maxPower'] > 30:
            upd['twoFourGhzSettings']['maxPower'] = 30
            print('Maximum power configurable for 2.4GHz is 30')
        del upd['id']
        del upd['networkId']
        del upd['name']
        del upd['bandSelectionType']
        dashboard.wireless.createNetworkWirelessRfProfile(networkId=dst_net_id, name=name,
                                                          bandSelectionType=band_selection_type, **upd)
    rf_profiles = dashboard.wireless.getNetworkWirelessRfProfiles(networkId=dst_net_id)
    for setting in radio_settings:
        upd = setting
        serial = setting['serial']
        for profile in rf_profiles:
            if 'profileName' in upd:
                if profile['name']==upd['profileName']:
                    upd['rfProfileId'] = profile['id']
        del upd['serial']
        dashboard.wireless.updateDeviceWirelessRadioSettings(serial=serial, **upd)

def ssid(dashboard, src_temp_id, dst_net_id, dst_org_id):
    """
    Gets the existing SSID configuration in the template, and applies it to the unbound network.
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :param dst_org_id: ID of organization
    """
    ssids = dashboard.wireless.getNetworkWirelessSsids(networkId=src_temp_id)
    actions = []
    for ssid in ssids:
        d = ssid
        upd = dict(d)
        if 'wifiPersonalNetworkEnabled' in upd:
            if upd['wifiPersonalNetworkEnabled'] == None:
                upd['wifiPersonalNetworkEnabled'] = False
        if 'encryptionMode' in upd:
            if upd['encryptionMode'] == 'wpa-eap':
                upd['encryptionMode'] = 'wpa'
                for server in upd['radiusServers']:
                    if server['caCertificate'] == None:
                        del server['caCertificate']
                    event, values = user_input(message=f"Please enter RADIUS secret for server {server['host']}: ")
                    server['secret'] = values["_INPUT_"]
                if 'radiusAccountingServers' in upd:
                    for server in upd['radiusAccountingServers']:
                        if server['caCertificate'] == None:
                            del server['caCertificate']
                        event, values = user_input(message=f"Please enter RADIUS secret for Accounting server {server['host']}: ")
                        server['secret'] = values["_INPUT_"]
                if upd['radiusFailoverPolicy'] == None:
                    del upd['radiusFailoverPolicy']
                if upd['radiusLoadBalancingPolicy'] == None:
                    del upd['radiusLoadBalancingPolicy']
        del upd['number']
        a = {
            "resource": f"/networks/{dst_net_id}/wireless/ssids/{d['number']}",
            "operation": "update",
            "body": {
                **upd
            }
        }
        actions.append(a)

    # Check for unfinished batches
    i = False
    while not i:
        print("Checking for unfinished batches")
        current_batches = dashboard.organizations.getOrganizationActionBatches(dst_org_id)
        unfinished_batches = []
        for b in current_batches:
            if b['status']['completed'] == False and b['status']['failed'] == False:
                unfinished_batches.append(b)

        if len(unfinished_batches) > 4:
            i = False
            print(f"You have {len(unfinished_batches)} unfinished batches:")
            for item in unfinished_batches:
                print(item)
            print("Waiting to complete some of these before scheduling a new one!")
            time.sleep(10)
        elif len(unfinished_batches) <= 4:
            i = True
    batch = dashboard.organizations.createOrganizationActionBatch(organizationId=dst_org_id,
                                                                  actions=actions, confirmed=True)

def ssid_firewall(dashboard, src_temp_id, dst_net_id, dst_org_id):
    """
    Gets the existing SSID firewall configuration in the template, and applies it to the unbound network.
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :param dst_org_id: ID of organization
    :return: 
    """
    actions = []
    for n in range(15):
        l3_fw = dashboard.wireless.getNetworkWirelessSsidFirewallL3FirewallRules(networkId=src_temp_id, number=n)
        l7_fw = dashboard.wireless.getNetworkWirelessSsidFirewallL7FirewallRules(networkId=src_temp_id, number=n)

        indices = []
        for i in range(len(l3_fw['rules'])):
            if l3_fw['rules'][i]['comment'] == 'Wireless clients accessing LAN':
                indices.append(i)
                if l3_fw['rules'][i]['policy']=='deny':
                    l3_fw['allowLanAccess'] = False
                else:
                    l3_fw['allowLanAccess'] = True
            elif l3_fw['rules'][i]['comment'] == 'Default rule':
                indices.append(i)
        for item in sorted(indices, reverse=True):
            l3_fw['rules'].pop(item)

        a = {
            "resource": f"/networks/{dst_net_id}/wireless/ssids/{n}/firewall/l7FirewallRules",
            "operation": "update",
            "body": {
                **l7_fw
            }
        }
        actions.append(a)
        dashboard.wireless.updateNetworkWirelessSsidFirewallL3FirewallRules(networkId=dst_net_id, number=n, **l3_fw)

    # Check for unfinished batches
    i = False
    while not i:
        print("Checking for unfinished batches")
        current_batches = dashboard.organizations.getOrganizationActionBatches(dst_org_id)
        unfinished_batches = []
        for b in current_batches:
            if b['status']['completed'] == False and b['status']['failed'] == False:
                unfinished_batches.append(b)

        if len(unfinished_batches) > 4:
            i = False
            print(f"You have {len(unfinished_batches)} unfinished batches:")
            for item in unfinished_batches:
                print(item['id'])
            print("Waiting to complete some of these before scheduling a new one!")
            time.sleep(10)
        elif len(unfinished_batches) <= 4:
            i = True

    dashboard.organizations.createOrganizationActionBatch(organizationId=dst_org_id, actions=actions,
                                                                     confirmed=True)

def ssid_shaping(dashboard, src_temp_id, dst_net_id, dst_org_id):
    """
    Obtains current SSID shaping rules in the template and applies to the unbound network.
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :param dst_org_id: ID of organization
    :return:
    """
    actions = []
    for i in range(15):
        shaping = dashboard.wireless.getNetworkWirelessSsidTrafficShapingRules(networkId=src_temp_id, number=i)
        a = {
            "resource": f"/networks/{dst_net_id}/wireless/ssids/{i}/trafficShaping/rules",
            "operation": "update",
            "body": {
                **shaping
            }
        }
        actions.append(a)
    # Check for unfinished batches
    i = False
    while not i:
        print("Checking for unfinished batches")
        current_batches = dashboard.organizations.getOrganizationActionBatches(dst_org_id)
        unfinished_batches = []
        for b in current_batches:
            if b['status']['completed'] == False and b['status']['failed'] == False:
                unfinished_batches.append(b)

        if len(unfinished_batches) > 4:
            i = False
            print(f"You have {len(unfinished_batches)} unfinished batches:")
            for item in unfinished_batches:
                print(item['id'])
            print("Waiting to complete some of these before scheduling a new one!")
            time.sleep(10)
        elif len(unfinished_batches) <= 4:
            i = True
    dashboard.organizations.createOrganizationActionBatch(organizationId=dst_org_id, actions=actions, confirmed=True)

def switch_qos(dashboard, src_temp_id, dst_net_id, dst_org_id):
    """
    Obtains existing switch QoS settings in template and applies to unbound network
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :param dst_org_id: ID of organization
    :return:
    """
    src_qos = dashboard.switch.getNetworkSwitchQosRules(networkId=src_temp_id)
    dst_qos_order = dashboard.switch.getNetworkSwitchQosRulesOrder(networkId=dst_net_id)
    actions = []
    # Delete all QoS rules in target template
    for item in dst_qos_order['ruleIds']:
        a = {
            "resource": f"/networks/{dst_net_id}/switch/qosRules/{item}",
            "operation": "destroy",
            "body": {}
        }
        actions.append(a)
    # Create new QoS rules in target template matching source template
    for item in src_qos:
        # Remove source port and destination port from payload if set to None/Nay
        # Handle exception where source/destination is a range, not individual port
        try:
            if item['srcPort'] == None and item['protocol'] != 'ANY':
                del item['srcPort']
        except KeyError:
            pass
        try:
            if item['dstPort'] == None and item['protocol'] != 'ANY':
                del item['dstPort']
        except KeyError:
            pass

        a = {
            "resource": f"/networks/{dst_net_id}/switch/qosRules",
            "operation": "create",
            "body": {
                **item
            }
        }
        actions.append(a)

    # Split actions in chunks of 20 to send synchronous batches and keep QoS Rule order
    batches = [actions[x:x + 20] for x in range(0, len(actions), 20)]

    # Create one synchronous action batch for every batch in batches
    for batch in batches:
        # Check for unfinished batches
        i = False
        while not i:
            print("Checking for unfinished batches")
            current_batches = dashboard.organizations.getOrganizationActionBatches(dst_org_id)
            unfinished_batches = []
            for b in current_batches:
                if b['status']['completed'] == False and b['status']['failed'] == False:
                    unfinished_batches.append(b)

            if len(unfinished_batches) > 4:
                i = False
                print(f"You have {len(unfinished_batches)} unfinished batches:")
                for item in unfinished_batches:
                    print(item['id'])
                print("Waiting to complete some of these before scheduling a new one!")
                time.sleep(10)
            elif len(unfinished_batches) <= 4:
                i = True

        dashboard.organizations.createOrganizationActionBatch(organizationId=dst_org_id, actions=batch, confirmed=True,
                                                              synchronous=True)

def switch_stp(dashboard, src_temp_id, src_org_id, dst_net_id, dst_org_id):
    """
    Obtains existing switch STP settings in template and applies to unbound network
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :param dst_org_id: ID of organization
    :return:
    """
    src_switch_profiles = dashboard.switch.getOrganizationConfigTemplateSwitchProfiles(
        organizationId=src_org_id, configTemplateId=src_temp_id)
    dst_switch_profiles = dashboard.switch.getOrganizationConfigTemplateSwitchProfiles(
        organizationId=dst_org_id, configTemplateId=dst_net_id)

    src_switch_set = [item['model'] for item in src_switch_profiles]
    dst_switch_set = [item['model'] for item in dst_switch_profiles]

    if src_switch_set == dst_switch_set:
        src_stp = dashboard.switch.getNetworkSwitchStp(networkId=src_temp_id)
        payload = src_stp
        dst_stp = dashboard.switch.getNetworkSwitchStp(networkId=dst_net_id)
        for i in range(len(src_stp['stpBridgePriority'])):
            for n in range(len(src_stp['stpBridgePriority'][i]['switchProfiles'])):
                for src_profile in src_switch_profiles:
                    if src_stp['stpBridgePriority'][i]['switchProfiles'][n] == src_profile['switchProfileId']:
                        for dst_profile in dst_switch_profiles:
                            if src_profile['model'] == dst_profile['model']:
                                src_stp['stpBridgePriority'][i]['switchProfiles'][n] = dst_profile['switchProfileId']
        dashboard.switch.updateNetworkSwitchStp(networkId=dst_net_id, **src_stp)

def group_policies(dashboard, src_temp_id, dst_net_id, dst_org_id):
    """
    Obtains existing group policies in template and applies to unbound network
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :param dst_org_id: ID of organization
    :return:
    """
    src_policies = dashboard.networks.getNetworkGroupPolicies(networkId=src_temp_id)
    dst_policies = dashboard.networks.getNetworkGroupPolicies(networkId=dst_net_id)

    actions = []
    for policy in dst_policies:
        a = {
            "resource": f"/networks/{dst_net_id}/groupPolicies/{policy['groupPolicyId']}",
            "operation": "destroy",
            "body": {}
        }
        actions.append(a)

    for policy in src_policies:
        dict = policy
        # Remove unneeded key from dict
        del dict['groupPolicyId']
        a = {
            "resource": f"/networks/{dst_net_id}/groupPolicies",
            "operation": "create",
            "body": {
                **dict
            }
        }
        actions.append(a)

    # Split actions in chunks of 20 to send synchronous batches and destroy existing policies before creating new ones
    batches = [actions[x:x + 20] for x in range(0, len(actions), 20)]

    # Create one synchronous action batch for every batch in batches
    for batch in batches:
        # Check for unfinished batches
        i = False
        while not i:
            print("Checking for unfinished batches")
            current_batches = dashboard.organizations.getOrganizationActionBatches(dst_org_id)
            unfinished_batches = []
            for b in current_batches:
                if b['status']['completed'] == False and b['status']['failed'] == False:
                    unfinished_batches.append(b)

            if len(unfinished_batches) > 4:
                i = False
                print(f"You have {len(unfinished_batches)} unfinished batches:")
                for item in unfinished_batches:
                    print(item['id'])
                print("Waiting to complete some of these before scheduling a new one!")
                time.sleep(10)
            elif len(unfinished_batches) <= 4:
                i = True

        dashboard.organizations.createOrganizationActionBatch(organizationId=dst_org_id, actions=batch, confirmed=True,
                                                              synchronous=True)
def switch_port_schedules(dashboard, dst_net_id, port_schedules):
    """
    Restores Port Schedules in the unbound network
    :return:
    """
    for ps in port_schedules:
        upd = {k: ps[k] for k in ps.keys() - {
            "id",
            "networkId",
            "name"
        }}
        dashboard.switch.createNetworkSwitchPortSchedule(networkId=dst_net_id, name=ps['name'], **upd)

def switch_access_policies(dashboard, dst_net_id, access_policies):
    """
    Restores Access Policies in the unbound network
    :return:
    """
    for ap in access_policies:
        access_policy_number = ap['accessPolicyNumber']
        name = ap['name']
        radius_servers = ap['radiusServers']
        event, values = user_input(message=f"Please input your desired RADIUS secret for Access Policy {name}: ")
        radius_secret = values["_INPUT_"]
        for server in radius_servers:
            server['secret'] = radius_secret
        radius_testing = ap['radiusTestingEnabled']
        radius_coa_support = ap['radiusCoaSupportEnabled']
        radius_acct_enabled = ap['radiusAccountingEnabled']
        if radius_acct_enabled == True:
            event, values = user_input(message=f"Please input your desired Accounting RADIUS secret for Access Policy {name}: ")
            radius_secret = values["_INPUT_"]
            for server in ap['radiusAccountingServers']:
                server['secret']=radius_secret
        host_mode = ap['hostMode']
        url_redirect_walled_garden_enabled = ap['urlRedirectWalledGardenEnabled']
        upd = {k: ap[k] for k in ap.keys() - {
            'accessPolicyNumber',
            'name',
            'radiusServers',
            'radiusTestingEnabled',
            'radiusCoaSupportEnabled',
            'radiusAccountingEnabled',
            'hostMode',
            'urlRedirectWalledGardenEnabled'
        }}
        dashboard.switch.createNetworkSwitchAccessPolicy(
            networkId=dst_net_id,
            name=name,
            radiusServers=radius_servers,
            radiusTestingEnabled=radius_testing,
            radiusCoaSupportEnabled=radius_coa_support,
            radiusAccountingEnabled=radius_acct_enabled,
            hostMode=host_mode,
            urlRedirectWalledGardenEnabled=url_redirect_walled_garden_enabled,
            **upd
        )

def switch_ports(dashboard, dst_net_id, dst_org_id, switch_port_configs):
    """
    Restores Switch Ports in the unbound network
    :return:
    """
    port_schedules = dashboard.switch.getNetworkSwitchPortSchedules(networkId=dst_net_id)
    access_policies = dashboard.switch.getNetworkSwitchAccessPolicies(networkId=dst_net_id)
    actions = []
    for key in switch_port_configs:
        for port in switch_port_configs[key]:
            upd = port
            del upd['linkNegotiationCapabilities']
            for schedule in port_schedules:
                if schedule['name']==upd['portScheduleId']:
                    upd['portScheduleId']=schedule['id']
            if port['type'] == 'access':
                if port['accessPolicyType'] != 'Open':
                    for policy in access_policies:
                        if policy['name'] == port['accessPolicyNumber']:
                            upd['accessPolicyNumber']=int(policy['accessPolicyNumber'])
            action = {
                "resource": f'/devices/{key}/switch/ports/{upd["portId"]}',
                "operation": 'update',
                "body": {k: upd[k] for k in upd.keys() - {'portId'}}
            }
            actions.append(action)
    for i in range(0, len(actions), 100):
        # Check for unfinished batches
        j = False
        while not j:
            print("Checking for unfinished batches")
            current_batches = dashboard.organizations.getOrganizationActionBatches(dst_org_id)
            unfinished_batches = []
            for b in current_batches:
                if b['status']['completed'] == False and b['status']['failed'] == False:
                    unfinished_batches.append(b)
            if len(unfinished_batches) > 4:
                j = False
                print(f"You have {len(unfinished_batches)} unfinished batches:")
                for item in unfinished_batches:
                    print(item['id'])
                print("Waiting to complete some of these before scheduling a new one!")
                time.sleep(10)
            elif len(unfinished_batches) <= 4:
                j = True
        subactions = actions[i:i + 100]
        dashboard.organizations.createOrganizationActionBatch(
            organizationId=dst_org_id,
            actions=subactions,
            confirmed=True,
            synchronous=False
        )
        time.sleep(1)
    pass

def switch_acl(dashboard, src_temp_id, dst_net_id):
    """
    Obtain existing Switch ACL configs in template and copies it to unbound network
    :param dashboard:
    :param src_temp_id:
    :param dst_net_id:
    :return:
    """
    acl = dashboard.switch.getNetworkSwitchAccessControlLists(src_temp_id)
    # Remove default rule
    acl['rules'].pop(-1)
    dashboard.switch.updateNetworkSwitchAccessControlLists(dst_net_id, acl['rules'])

def net_alerts(dashboard, src_temp_id, dst_net_id):
    """
    Obtains existing alert settings in template and applies to unbound network
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :return:
    """
    src_alerts = dashboard.networks.getNetworkAlertsSettings(networkId=src_temp_id)
    dst_alerts = dashboard.networks.getNetworkAlertsSettings(networkId=dst_net_id)

    for i in range(len(dst_alerts['alerts'])):
        for src_alert in src_alerts['alerts']:
            if dst_alerts['alerts'][i]['type'] == src_alert['type']:
                if src_alert != dst_alerts['alerts'][i]:
                    dst_alerts['alerts'][i] = src_alert

    # Remove clientConnectivity alerts, as they give issues when updating
    for i in range(len(dst_alerts['alerts'])):
        if dst_alerts['alerts'][i]['type'] == 'clientConnectivity':
            p = i
            dst_alerts['alerts'].pop(p)
    dashboard.networks.updateNetworkAlertsSettings(networkId=dst_net_id, **dst_alerts)

def net_syslog(dashboard, src_temp_id, dst_net_id):
    """
    Obtains existing syslog settings in template and applies to unbound network
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :return:
    """
    src_syslog = dashboard.networks.getNetworkSyslogServers(networkId=src_temp_id)
    dashboard.networks.updateNetworkSyslogServers(networkId=dst_net_id, servers=src_syslog['servers'])

def net_snmp(dashboard, src_temp_id, dst_net_id):
    """
    Obtains existing SNMP settings in template and applies to unbound network
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :return:
    """
    src_snmp = dashboard.networks.getNetworkSnmp(networkId=src_temp_id)
    dashboard.networks.updateNetworkSnmp(networkId=dst_net_id, **src_snmp)

def net_analytics(dashboard, src_temp_id, dst_net_id):
    """
    Obtains existing analytics settings in template and applies to unbound network
    :param dashboard: Dashboard API client instance
    :param src_temp_id: ID of source template
    :param dst_net_id: ID of unbound network
    :return:
    """
    src_ta = dashboard.networks.getNetworkTrafficAnalysis(networkId=src_temp_id)
    dashboard.networks.updateNetworkTrafficAnalysis(networkId=dst_net_id, **src_ta)
