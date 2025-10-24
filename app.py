from flask import Flask, request, jsonify, render_template
from netmiko import ConnectHandler
import time
import re
import json

app = Flask(__name__)

def processar_output_ont(output, olt_ip):
    
    # Extrai fsp, ont_id, sn, run_state e description do output da OLT Huawei (display ont info by-desc).
    # Retorna lista de dicionários.
    

    # 1) padrão que identifica as linhas da tabela com SN e run state
    sn_pattern = re.compile(
        r'^\s*(?P<fsp>\d+/\s*\d+/\d+)\s+'
        r'(?P<ont_id>\d+)\s+'
        r'(?P<sn>[0-9A-Fa-f]{8,})\s+'      # SN (hex) - pelo menos 8 chars
        r'\S+\s+'                          # campo "Control flag" (qualquer token)
        r'(?P<run_state>\w+)',             # run state (online/offline)
        re.MULTILINE
    )

    # 2) padrão que tenta capturar a linha da description (terceira tabela)
    desc_pattern = re.compile(
        r'^\s*(?P<fsp>\d+/\s*\d+/\d+)\s+'
        r'(?P<ont_id>\d+)\s+'
        r'(?P<description>.+\S)\s*$',
        re.MULTILINE
    )

    # dicionário temporário indexado por (fsp,ont_id)
    entries = {}

    # percorre e popula sn/run_state
    for m in sn_pattern.finditer(output):
        fsp = m.group('fsp').replace(' ', '')
        ont_id = m.group('ont_id')
        entries[(fsp, ont_id)] = {
            "fsp": fsp,
            "ont_id": ont_id,
            "sn": m.group('sn'),
            "run_state": m.group('run_state'),
            "description": "",
	        "olt_ip": olt_ip
        }

    # percorre possíveis linhas de description e associa
    for m in desc_pattern.finditer(output):
        fsp = m.group('fsp').replace(' ', '')
        ont_id = m.group('ont_id')
        desc = m.group('description').strip()

        # se a primeira "palavra" da descrição for um SN (apenas hex), pule — é uma linha SN, não description
        first_token = desc.split()[0] if desc else ""
        if re.fullmatch(r'[0-9A-Fa-f]{8,}', first_token):
            continue  # ignora: essa linha é parte da tabela SN

        key = (fsp, ont_id)
        if key in entries:
            entries[key]['description'] = desc
        else:
            # se não existir a entrada (descreve uma linha sem SN detectado antes), crie mesmo assim
            entries[key] = {
                "fsp": fsp,
                "ont_id": ont_id,
                "sn": None,
                "run_state": None,
                "description": desc,
		        "olt_ip": olt_ip
            }

    # retorna a lista de valores
    return list(entries.values())

def buscar_sinal_ont(olt_ip, onts):    
    # Atualiza a lista de ONTs com o sinal óptico (se online) ou alarm-state (se offline)

    # Conecta na OLT
    device = acesso(olt_ip)

    ssh = ConnectHandler(**device)
    ssh.send_command("enable", expect_string=r"#", read_timeout=10)
    ssh.send_command("config", expect_string=r"\(config\)#", read_timeout=10)

    # Agrupa ONTs por frame/slot
    slot_groups = defaultdict(list)
    for ont in onts:
        frame, slot, pon = map(int, ont['fsp'].split('/'))
        slot_groups[(frame, slot)].append(ont)

    for (frame, slot), ont_group in slot_groups.items():
        ssh.send_command(f"interface gpon {frame}/{slot}", expect_string=r"\(config-if-gpon", read_timeout=10) #Acessa a interface GPON do slot da OLT 

        # Dividir ONTs online e offline
        online_onts = [ont for ont in ont_group if ont['run_state'] == "online"] #ONTs ONLINE
        offline_onts = [ont for ont in ont_group if ont['run_state'] != "online"] #ONTs OFFLINE

        # --- ONTs ONLINE ---
        if online_onts:
            # Executa comando uma vez para todos os PONs do slot
            # Precisa iterar por PON porque display ont optical-info <pon> <ont_id>
            for ont in online_onts:
                pon = int(ont['fsp'].split('/')[2])
                ont_id = int(ont['ont_id'])
                output = ssh.send_command(f"display ont optical-info {pon} {ont_id}", read_timeout=15) #Comando para buscar sinal óptico da ONU

                match = re.search(r"Rx optical power\(dBm\)\s*:\s*([-\d.]+)", output)
                ont['rx_power'] = float(match.group(1)) if match else None #Valor do sinal óptico em dBm

        # --- ONTs OFFLINE ---
        if offline_onts:
            for ont in offline_onts:
                pon = int(ont['fsp'].split('/')[2])
                ont_id = int(ont['ont_id'])
                output = ssh.send_command(f"display ont alarm-state {pon} {ont_id}", read_timeout=10) #Comando para buscar alarm-state da ONU

                match = re.search(r"Active Alarm List\s*:\s*\n\s*\((?:\d+)\)(.+)", output, re.IGNORECASE)
                ont['alarm'] = match.group(1).strip() if match else None 

    ssh.disconnect()
    return onts

def acesso(olt_ip):
    # Retorna um dicionário de conexão para a OLT Huawei.
    olt = {
        "device_type": "huawei_smartax",
        "ip": olt_ip,
        "username": "?",
        "password": "?",
        "port": 22
    }
    return olt

def libera_onu(fsp, olt_ip):
    # Libera a ONU na OLT Huawei dado o fsp (frame/slot/pon/ont_id) e o IP da OLT.
    device = acesso(olt_ip)

    #Executa a liberação de acesso via http por linha de comando na OLT

    try:
        device = acesso(olt_ip)

        ssh = ConnectHandler(**device)
        ssh.send_command("enable", expect_string=r"#", read_timeout=10)
        ssh.send_command("diagnose", expect_string=r"\(diagnose\)%%", read_timeout=10)
        output = ssh.send_command(f"ont wan-access http {fsp} enable") #Comando de liberação da ONU via HTTP
        ssh.disconnect()

        return {"status": "ok", "mensagem": output}

    except Exception as e:
        return {"status": "erro", "mensagem": str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/olt/', methods=['POST'])
def status_olt():
    # Recebe dados do cliente e consulta a OLT Huawei, retornando o status da ONU e outras informações.

    dados = request.get_json()
    olt_ip = dados["olt"]
    cliente = dados["cliente"]
    
    olt = acesso(olt_ip)    
    try:
        ssh = ConnectHandler(**olt)
        ssh.send_command("enable", expect_string=r"#", read_timeout=10)

        output = ssh.send_command(f"display ont info by-desc {cliente.lower()}", read_timeout=25) #Comando para buscar a ONU pelo nome/descritivo
        ssh.disconnect()

        dados = processar_output_ont(output, olt_ip)

        dados_atualizados = buscar_sinal_ont(olt_ip, dados)
        return jsonify(dados_atualizados)

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


@app.route('/olt/unlocked/', methods=['POST'])
def unlockedBtn():
    # Recebe dados do cliente e libera a ONU na OLT
    dados = request.get_json()
    infos = dados['onu'].split(',')
    olt_ip = infos[0]
    fsp = infos[1]

    dados = libera_onu(fsp, olt_ip)

    return jsonify(dados)

@app.route('/olt/reboot/', methods=['POST'])
def reboot_onu():
    # Recebe dados da ONU e realiza o reboot na OLT Huawei
    dados = request.get_json()
    infos = dados['onu'].split(',')
    olt_ip = infos[0]
    fsp = infos[1]
    device = acesso(olt_ip)
    try:
        ssh = ConnectHandler(**device)
        ssh.send_command("enable", expect_string=r"#", read_timeout=10)
        ssh.send_command("diagnose", expect_string=r"\(diagnose\)%%", read_timeout=10)
        output = ssh.send_command_timing(f"ont force-reset {fsp}") #Comando de reboot da ONU
        
        # Se for solicitado confirmação, envia "y" para confirmar o reboot
        if "Are you sure to reset" in output: 
            output += ssh.send_command_timing("y")

        ssh.disconnect()
        return jsonify({"status": "ok", "mensagem": output})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=169, debug=True)