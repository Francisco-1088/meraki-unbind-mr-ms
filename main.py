import meraki
import PySimpleGUI as sg
import credentials
import functions

if __name__ == "__main__":
    # Change print_console to True if you want to see console output
    dashboard = meraki.DashboardAPI(api_key=credentials.api_key,log_path="logs", print_console=False)
    if credentials.org_id != '':
        org_templates = functions.gather_templates(dashboard, org_id=credentials.org_id)
    else:
        org_templates = functions.gather_templates(dashboard)
    org_temp_list = []
    template_networks_dict = {}
    for org in org_templates:
        for temp in org['templates']:
            item = {'name': org['name']+' - '+ temp['name'], 'id':temp['id'], 'org_id': org['id'], 'prodTypes':temp['productTypes']}
            org_temp_list.append(item)
            net_list = []
            for net in temp['networks']:
                item = {'name': net['name'], "id": net['id'], 'prodTypes': net['productTypes']}
                net_list.append(item)
            template_networks_dict[f"{temp['id']}"]=net_list
    error_list = []

    sg.ChangeLookAndFeel('LightGreen')
    options = {"enable_events": True}
    layout = [
        [sg.Text('Source Template  '), sg.Combo([temp['name'] for temp in org_temp_list], **options, key='_SRC_TMP_')],
        [sg.Text('Network to Unbind  '), sg.Combo((), **options, key='_DST_NET_')],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Wireless - SSIDs', key='_SSID_', size=(40,1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Wireless - SSID Firewall', key='_FW_', size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Wireless - SSID Traffic Shaping', key="_SHAPE_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Wireless - Radio Settings', key="_RADIO_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Switch - Ports', key="_PORT_PRF_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Switch - QoS Settings', key="_QOS_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Switch - STP Settings', key="_STP_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Switch - ACL', key="_ACL_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Network - Group Policies', key="_GP_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Network - Alerts', key="_ALERT_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Network - Syslog', key="_SYSLOG_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Network - SNMP', key="_SNMP_", size=(40, 1))],
        [sg.Text(' ' * 8), sg.Checkbox('Preserve Network - Traffic Analysis', key="_ANALYTICS_", size=(40, 1))],
        [sg.Button('OK', key="_OK_"), sg.Button('Cancel', key="_CANCEL_")]
    ]
    win = sg.Window('Unbind and Retain MR/MS configs from templates',
                    default_element_size=(20, 1),
                    text_justification='right',
                    auto_size_text=False,
                    font=('Helvetica', 20)).Layout(layout)
    j = True
    while j:
        event, values = win.Read()
        if event == '_CANCEL_':
            exit()
        elif event == "_SRC_TMP_":
            for i in range(len(org_temp_list)):
                if org_temp_list[i]['name'] == values[event]:
                    src_temp_id = org_temp_list[i]['id']
            win['_DST_NET_'].Update(value=[],values=template_networks_dict[src_temp_id])
        elif event == '_OK_':
            src_temp = values['_SRC_TMP_']
            dst_net = values['_DST_NET_']
            preserve_ssids = values['_SSID_']
            preserve_switch_ports = values['_PORT_PRF_']
            preserve_ssid_fw = values['_FW_']
            preserve_ssid_ts = values['_SHAPE_']
            preserve_radio_settings = values['_RADIO_']
            preserve_switch_qos = values['_QOS_']
            preserve_switch_stp = values['_STP_']
            preserve_switch_acl = values['_ACL_']
            preserve_net_gps = values['_GP_']
            preserve_net_alerts = values['_ALERT_']
            preserve_net_syslog = values['_SYSLOG_']
            preserve_net_snmp = values['_SNMP_']
            preserve_net_ta = values['_ANALYTICS_']
            args = values
            j = False

    win.Close()

    for i in range(len(org_temp_list)):
        if org_temp_list[i]['name']==src_temp:
            src_temp_id = org_temp_list[i]['id']
            src_org_id = org_temp_list[i]['org_id']
            src_temp_prods = org_temp_list[i]['prodTypes']
    dst_net_id = dst_net['id']
    dst_org_id = src_org_id
    dst_net_prods = dst_net['prodTypes']

    win_started = False
    try:
        if preserve_switch_ports:
            if 'switch' not in src_temp_prods:
                error = 'Your source template does not have switch products, so you cannot copy ports from it.'
                functions.open_window(error)
            elif 'switch' not in dst_net_prods:
                error = 'Your destination template does not have switch products, so you cannot copy ports to it.'
                functions.open_window(error)
            else:
                try:
                    stp, access_policies, port_schedules, switch_port_configs = functions.get_switch_configs(dashboard, dst_net_id)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)
        if preserve_radio_settings:
            if 'wireless' not in src_temp_prods:
                error = 'Your source template does not have wireless products, so you cannot copy Radio Settings from it.'
                functions.open_window(error)
            elif 'wireless' not in dst_net_prods:
                error = 'Your destination template does not have wireless products, so you cannot copy Radio Settings to it.'
                functions.open_window(error)
            else:
                try:
                    radio_settings = functions.get_rfprofiles(dashboard, src_temp_id, dst_net_id)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)
        # Unbind network from template
        unbind = dashboard.networks.unbindNetwork(dst_net_id)
        if preserve_ssids:
            if 'wireless' not in src_temp_prods:
                error = 'Your source template does not have wireless products, so you cannot copy SSIDs from it.'
                functions.open_window(error)
            elif 'wireless' not in dst_net_prods:
                error = 'Your destination template does not have wireless products, so you cannot copy SSIDs to it.'
                functions.open_window(error)
            else:
                try:
                    functions.ssid(dashboard=dashboard, src_temp_id=src_temp_id, dst_net_id=dst_net_id,dst_org_id=dst_org_id)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_switch_ports:
            if 'switch' not in src_temp_prods:
                error = 'Your source template does not have switch products, so you cannot copy ports from it.'
                functions.open_window(error)
            elif 'switch' not in dst_net_prods:
                error = 'Your destination template does not have switch products, so you cannot copy ports to it.'
                functions.open_window(error)
            else:
                try:
                    functions.switch_port_schedules(dashboard, dst_net_id, port_schedules)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)
                try:
                    functions.switch_access_policies(dashboard, dst_net_id, access_policies)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)
                try:
                    functions.switch_ports(dashboard, dst_net_id, dst_org_id, switch_port_configs)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_radio_settings:
            if 'wireless' not in src_temp_prods:
                error = 'Your source template does not have wireless products, so you cannot copy Radio Settings from it.'
                functions.open_window(error)
            elif 'wireless' not in dst_net_prods:
                error = 'Your destination template does not have wireless products, so you cannot copy Radio Settings to it.'
                functions.open_window(error)
            else:
                try:
                    functions.restore_rf_profiles(dashboard, src_temp_id, dst_net_id, radio_settings)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_ssid_fw:
            if 'wireless' not in src_temp_prods:
                error = 'Your source template does not have wireless products, so you cannot copy SSIDs from it.'
                functions.open_window(error)
            elif 'wireless' not in dst_net_prods:
                error = 'Your destination template does not have wireless products, so you cannot copy SSIDs to it.'
                functions.open_window(error)
            else:
                try:
                    functions.ssid_firewall(dashboard=dashboard, src_temp_id=src_temp_id,dst_net_id=dst_net_id,dst_org_id=dst_org_id)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_ssid_ts:
            if 'wireless' not in src_temp_prods:
                error = 'Your source template does not have wireless products, so you cannot copy SSIDs from it.'
                functions.open_window(error)
            elif 'wireless' not in dst_net_prods:
                error = 'Your destination template does not have wireless products, so you cannot copy SSIDs to it.'
                functions.open_window(error)
            else:
                try:
                    functions.ssid_shaping(dashboard=dashboard, src_temp_id=src_temp_id, dst_org_id=dst_org_id, dst_net_id=dst_net_id)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_switch_qos:
            if 'switch' not in src_temp_prods:
                error = 'Your source template does not have switch products, so you cannot copy ports from it.'
                functions.open_window(error)
            elif 'switch' not in dst_net_prods:
                error = 'Your destination template does not have switch products, so you cannot copy ports to it.'
                functions.open_window(error)
            else:
                try:
                    functions.switch_qos(dashboard=dashboard, src_temp_id=src_temp_id, dst_net_id=dst_net_id,dst_org_id=dst_org_id)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_switch_stp:
            if 'switch' not in src_temp_prods:
                error = 'Your source template does not have switch products, so you cannot copy ports from it.'
                functions.open_window(error)
            elif 'switch' not in dst_net_prods:
                error = 'Your destination template does not have switch products, so you cannot copy ports to it.'
                functions.open_window(error)
            else:
                try:
                    dashboard.switch.updateNetworkSwitchStp(dst_net_id,**stp)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_switch_acl:
            if 'switch' not in src_temp_prods:
                error = 'Your source template does not have switch products, so you cannot copy Switch ACLs from it.'
                functions.open_window(error)
            elif 'switch' not in dst_net_prods:
                error = 'Your destination template does not have switch products, so you cannot  cannot copy Switch ACLs to it.'
                functions.open_window(error)
            else:
                try:
                    functions.switch_acl(dashboard, src_temp_id, dst_net_id)
                except meraki.APIError as e:
                    functions.open_window(e)
                    error_list.append(e)

        if preserve_net_gps:
            try:
                functions.group_policies(dashboard=dashboard,src_temp_id=src_temp_id,dst_net_id=dst_net_id, dst_org_id=dst_org_id)
            except meraki.APIError as e:
                functions.open_window(e)
                error_list.append(e)
        if preserve_net_alerts:
            try:
                functions.net_alerts(dashboard=dashboard, src_temp_id=src_temp_id, dst_net_id=dst_net_id)
            except meraki.APIError as e:
                functions.open_window(e)
                error_list.append(e)
        if preserve_net_syslog:
            try:
                functions.net_syslog(dashboard=dashboard, src_temp_id=src_temp_id, dst_net_id=dst_net_id)
            except meraki.APIError as e:
                functions.open_window(e)
                error_list.append(e)
        if preserve_net_snmp:
            try:
                functions.net_snmp(dashboard=dashboard, src_temp_id=src_temp_id, dst_net_id=dst_net_id)
            except meraki.APIError as e:
                functions.open_window(e)
                error_list.append(e)
        if preserve_net_ta:
            try:
                functions.net_analytics(dashboard=dashboard, src_temp_id=src_temp_id, dst_net_id=dst_net_id)
            except meraki.APIError as e:
                functions.open_window(e)
                error_list.append(e)
        if error_list != []:
            event = functions.rollback_window(error_list, dashboard, src_temp_id, dst_net_id, lines=16, width=28)
        if event:
            if event == 'NO':
                success = 'Your network was unbinded and retained its configs successfully!'
                functions.open_window(success)
        else:
            success = 'Your network was unbinded and retained its configs successfully!'
            functions.open_window(success)
    except meraki.APIError as e:
        functions.open_window(e)
        error_list.append(e)
