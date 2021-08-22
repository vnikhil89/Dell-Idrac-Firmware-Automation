# _author_ = Nikhil Verma
# _version_ = 1.0

import requests, json, sys, re, time, warnings, argparse, os, csv, ssl, getpass, subprocess

from datetime import datetime
from pyVmomi import vim
from pyVim.connect import SmartConnect,Disconnect
from pyVim.task import WaitForTask
from packaging import version


warnings.filterwarnings("ignore")

def check_job_status():
    while True:
        req = requests.get('https://%s/redfish/v1/TaskService/Tasks/%s' % (idrac_ip, job_id), auth=(idrac_username, idrac_password), verify=False)
        statusCode = req.status_code
        data = req.json()
        if data["TaskState"] == "Completed":
            print("\n- PASS, job ID %s successfuly marked completed, detailed final job status results:\n" % data[u"Id"])
            for i in data['Oem']['Dell'].items():
                print("%s: %s" % (i[0],i[1]))
            print("\n- JOB ID %s completed in %s" % (job_id, current_time))
        current_time = str(datetime.now()-start_time)[0:7]   
        statusCode = req.status_code
        data = req.json()
        message_string=data["Messages"]
        if statusCode == 202 or statusCode == 200:
            pass
        else:
            print("Query job ID command failed, error code is: %s" % statusCode)
            sys.exit()
        if str(current_time)[0:7] >= "0:30:00":
            print("\n- FAIL: Timeout of 30 minutes has been hit, update job should of already been marked completed. Check the iDRAC job queue and LC logs to debug the issue\n")
            sys.exit()
        elif "failed" in data['Oem']['Dell']['Message'] or "completed with errors" in data['Oem']['Dell']['Message'] or "Failed" in data['Oem']['Dell']['Message']:
            print("- FAIL: Job failed, current message is: %s" % data["Messages"])
            sys.exit()
        elif "scheduled" in data['Oem']['Dell']['Message']:
            print("\n- PASS, job ID %s successfully marked as scheduled" % data["Id"])
            break
        elif "completed successfully" in data['Oem']['Dell']['Message']:
            print("\n- PASS, job ID %s successfully marked completed, detailed final job status results:\n" % data["Id"])
            for i in data['Oem']['Dell'].items():
                print("%s: %s" % (i[0],i[1]))
            print("\n- %s completed in: %s" % (job_id, str(current_time)[0:7]))
            break
        else:
            print("- Message: %s, current update execution time: %s" % (message_string[0]["Message"], current_time))
            time.sleep(1)
            continue

def esxi_mm():
    s = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
    s.verify_mode = ssl.CERT_NONE
    vc = da['vc_name']
    hostname = da["vc_hostname"]
    try:
        c = SmartConnect(host=vc, user=u, pwd=p)
        print('Valid certificate')
    except:
        c = SmartConnect(host=vc, user=u, pwd=p, sslContext=s)
        print('Invalid or untrusted certificate')

    datacenter = c.content.rootFolder.childEntity[0]
    cluster = datacenter.hostFolder.childEntity[0]
    hostnames = cluster.host
    mm_mode=vim.vsan.host.DecommissionMode(objectAction='ensureObjectAccessibility')
    spec = vim.host.MaintenanceSpec(vsanMode=mm_mode)
    for h in hostnames:
        if h.name == hostname:
            print ("Putting Host in Maintenace Mode ... "),
            try:
                WaitForTask(h.EnterMaintenanceMode_Task(0,True,spec))
                print ("Completed")
                try:
                    h.RebootHost_Task(False)
                    print("Host Rebooting")
                    time.sleep(300)
                except:
                    print("Host Failed to reboot")
            except:
                print ('Failed')
            
    Disconnect(c)
    
def check_host_connection():
    count = 0
    hostname = da["vc_hostname"]
    ping_command="ping %s -n 5" % hostname
    print(ping_command)
    while True:
        if count == 11:
            print("- WARNING, unable to successfully ping Hostname after 10 attempts, script will exit.")
            sys.exit()
        try:
            ping_output = subprocess.Popen(ping_command, stdout = subprocess.PIPE, shell=True).communicate()[0]
            ping_results = re.search("Lost = .", ping_output).group()
            if ping_results == "Lost = 0":
                break
            else:
                print("\n- INFO, Host Still not reachable. Script will recheck Host connection in 2 minute")
                time.sleep(120)
                count+=1
        except:
            ping_output = subprocess.run(ping_command,universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if "Lost = 0" in ping_output.stdout:
                break
            else:
                print("\n- INFO, Host Still not reachable. Script will recheck Host connection in 2 minute")
                time.sleep(120)
                count+=1
                
def esxi_exit_mm():
    s = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
    s.verify_mode = ssl.CERT_NONE
    vc = da['vc_name']
    hostname = da["vc_hostname"]
    try:
        c = SmartConnect(host=vc, user=u, pwd=p)
        print('Valid certificate')
    except:
        c = SmartConnect(host=vc, user=u, pwd=p, sslContext=s)
        print('Invalid or untrusted certificate')

    datacenter = c.content.rootFolder.childEntity[0]
    cluster = datacenter.hostFolder.childEntity[0]
    hostnames = cluster.host
    for h in hostnames:
        if h.name == hostname:
            print ("Removing Host from Maintenace Mode ... "),
            while True:
                if h.overallStatus == 'red':
                    print(h.overallStatus)
                    time.sleep(60)
                else:
                    try:
                        WaitForTask(h.ExitMaintenanceMode_Task(0))
                        print ("Completed")
                    except:
                        print ('Failed')
                    break
            
    Disconnect(c)

fo = open(r"InputFile.csv")
data = list (csv.DictReader(fo))
result = []
device_list = {}
global u
u = input("Enter the user name:")
global p
p=getpass.getpass(prompt='Enter Username password:')
global Idracpassword
Idracpassword = getpass.getpass(prompt='Enter Idrac password:')
for da in data:
    idrac_ip = da['IdracIP']
    idrac_username = da['Idracusername']
    idrac_password = Idracpassword
    print("\n- INFO, current devices detected with firmware version and updateable status -\n")
    req = requests.get('https://%s/redfish/v1/UpdateService/FirmwareInventory/' % (idrac_ip), auth=(idrac_username, idrac_password), verify=False)
    statusCode = req.status_code
    installed_devices=[]
    data = req.json()
    for i in data['Members']:
        for ii in i.items():
            if "Installed" in ii[1]:
                installed_devices.append(ii[1])
    for i in installed_devices:
        req = requests.get('https://%s%s' % (idrac_ip, i), auth=(idrac_username, idrac_password), verify=False)
        statusCode = req.status_code
        data1 = req.json()
        data = data1['Name']
        ph = r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}"
        if(re.search(ph, data)):
            data=data.split(" - ")
            data=data[0]
        else:
            data=data
        if "PCIe SSD" in data:
            data = data.split(" in ")
            data=data[0]
        else:
            data=data
        if "Integrated Remote Access Controller" in data:
            data = data.replace('Integrated Remote Access Controller','Integrated Dell Remote Access Controller')
        else:
            data=data
        device_list[data] = data1['Version']

    print(len(device_list))
    bios_version = device_list['BIOS']
    ssd_version  = device_list['PCIe SSD']
    network_version= device_list['Broadcom Adv. Dual 25Gb Ethernet']
    idrac_version = device_list['Integrated Dell Remote Access Controller']
    print("Bios Version: %s" % (bios_version))
    print("SSD Version: %s" %(ssd_version))
    print("IDRAC Version: %s" %(idrac_version))
    filopen = open(r"firmware-version.csv")
    data1 = list (csv.DictReader(filopen))
    print("Comparing Firmware Version as per provided firmware-version.csv")
    for x in data1:
        biosver = x['Bios']
        if version.parse(bios_version) < version.parse(biosver):
            print("Installing New Bios version in %s" %(idrac_ip))
            result = biosver
            global start_time
            start_time=datetime.now()
            print("\n- INFO, downloading \"%s\" image, this may take a few minutes depending on the size of the image" % x["Bios-exe-name"])
            url = "https://%s/redfish/v1/UpdateService/MultipartUpload" % idrac_ip
            path_bios = 'C:\\idrac-version\\%s' % x["Bios-exe-name"]
            print(path_bios)
            payload = {"Targets": [], "@Redfish.OperationApplyTime": "OnReset", "Oem": {}}
            files = {
                'UpdateParameters': (None, json.dumps(payload), 'application/json'),
                'UpdateFile': (os.path.basename(path_bios), open(path_bios, 'rb'), 'application/octet-stream')
            }
            response = requests.post(url, files=files, auth = (idrac_username, idrac_password), verify=False)
            if response.status_code == 202:
                pass
            else:
                data = response.json()
                print("- FAIL, status code %s returned, detailed error is: %s" % (response.status_code,data))
                sys.exit()
            try:
                job_id = response.headers['Location'].split("/")[-1]
            except:
                print("- FAIL, unable to locate job ID in header")
                sys.exit()
            print("- PASS, update job ID %s successfully created, script will now loop polling the job status\n" % job_id)
            if __name__ == "__main__":
                check_job_status()
        else:
            print("Correct Bios Version installed")
        
        ssdver = x['SSD Firmware']
        if version.parse(ssd_version) < version.parse(ssdver):
            print("Installing New SSD version in %s" %(idrac_ip))
            result = ssdver
            start_time=datetime.now()
            print("\n- INFO, downloading \"%s\" image, this may take a few minutes depending on the size of the image" % x["ssd-exe-name"])
            url = "https://%s/redfish/v1/UpdateService/MultipartUpload" % idrac_ip
            path_ssd = 'C:\\idrac-version\\%s' % x["ssd-exe-name"]
            print(path_ssd)
            payload = {"Targets": [], "@Redfish.OperationApplyTime": "OnReset", "Oem": {}}
            files = {
                'UpdateParameters': (None, json.dumps(payload), 'application/json'),
                'UpdateFile': (os.path.basename(path_ssd), open(path_ssd, 'rb'), 'application/octet-stream')
            }
            response = requests.post(url, files=files, auth = (idrac_username, idrac_password), verify=False)
            if response.status_code == 202:
                pass
            else:
                data = response.json()
                print("- FAIL, status code %s returned, detailed error is: %s" % (response.status_code,data))
                sys.exit()
            try:
                job_id = response.headers['Location'].split("/")[-1]
            except:
                print("- FAIL, unable to locate job ID in header")
                sys.exit()
            print("- PASS, update job ID %s successfully created, script will now loop polling the job status\n" % job_id)
            if __name__ == "__main__":
                check_job_status()
        else:
            print("Correct SSD Version installed")
        networkver = x['network firmware']
        if version.parse(network_version) < version.parse(networkver):
            print("Installing New Network version in %s" %(idrac_ip))
            result = networkver
            start_time=datetime.now()
            print("\n- INFO, downloading \"%s\" image, this may take a few minutes depending on the size of the image" % x["network-exe-name"])
            url = "https://%s/redfish/v1/UpdateService/MultipartUpload" % idrac_ip
            path_ssd = 'C:\\idrac-version\\%s' % x["network-exe-name"]
            print(path_ssd)
            payload = {"Targets": [], "@Redfish.OperationApplyTime": "OnReset", "Oem": {}}
            files = {
                'UpdateParameters': (None, json.dumps(payload), 'application/json'),
                'UpdateFile': (os.path.basename(path_ssd), open(path_ssd, 'rb'), 'application/octet-stream')
            }
            response = requests.post(url, files=files, auth = (idrac_username, idrac_password), verify=False)
            if response.status_code == 202:
                pass
            else:
                data = response.json()
                print("- FAIL, status code %s returned, detailed error is: %s" % (response.status_code,data))
                sys.exit()
            try:
                job_id = response.headers['Location'].split("/")[-1]
            except:
                print("- FAIL, unable to locate job ID in header")
                sys.exit()
            print("- PASS, update job ID %s successfully created, script will now loop polling the job status\n" % job_id)
            if __name__ == "__main__":
                check_job_status()
        else:
            print("Correct Network Version installed")
        idracver = x['Integrated Dell Remote Access Controller']
        if version.parse(idrac_version) < version.parse(idracver):
            print("Installing New Idrac version in %s" %(idrac_ip))
            result = idracver
            start_time=datetime.now()
            print("\n- INFO, downloading \"%s\" image, this may take a few minutes depending on the size of the image" % x["idrac-exe-name"])
            url = "https://%s/redfish/v1/UpdateService/MultipartUpload" % idrac_ip
            path_idrac = 'C:\\idrac-version\\%s' % x["idrac-exe-name"]
            print(path_idrac)
            payload = {"Targets": [], "@Redfish.OperationApplyTime": "OnReset", "Oem": {}}
            files = {
                'UpdateParameters': (None, json.dumps(payload), 'application/json'),
                'UpdateFile': (os.path.basename(path_idrac), open(path_idrac, 'rb'), 'application/octet-stream')
            }
            response = requests.post(url, files=files, auth = (idrac_username, idrac_password), verify=False)
            if response.status_code == 202:
                pass
            else:
                data = response.json()
                print("- FAIL, status code %s returned, detailed error is: %s" % (response.status_code,data))
                sys.exit()
            try:
                job_id = response.headers['Location'].split("/")[-1]
            except:
                print("- FAIL, unable to locate job ID in header")
                sys.exit()
            print("- PASS, update job ID %s successfully created, script will now loop polling the job status\n" % job_id)
            if __name__ == "__main__":
                check_job_status()
        else:
            print("Correct Idrac Version installed")
        print("Firmware need to update :%s" % len(result))
        if __name__ == "__main__":
            if len(result) == 0:
                print("No changes needed")
                #sys.exit()
            else:
                esxi_mm()
                check_host_connection()
                print("Host Reboot completed")
                esxi_exit_mm()
                #sys.exit()