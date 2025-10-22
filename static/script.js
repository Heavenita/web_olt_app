document.addEventListener('DOMContentLoaded', function () {
    const loadingOverlay = document.getElementById('loadingOverlay');
    const jsonOverlay = document.getElementById('jsonOverlay');
    const jsonContainer = document.getElementById('jsonContainer');
    const closeJson = document.getElementById('closeJson');
    const btn = document.getElementById('btnPesquisar');
    const unlockedBtn = document.getElementById('unlockedBtn');

    document.addEventListener('keydown', function (enter) {
        // Acionar busca ao pressionar Enter.
        if (enter.key === "Enter") {
            document.getElementById('btnPesquisar').click();
        }
    });

    btn.addEventListener('click', function () {
        // Buscar status da ONU.
        const modo = document.querySelector('input[name="modo"]:checked');
        if (!modo) { alert("Selecione uma OLT!"); return; }

        const cliente = document.getElementById('cliente').value.trim();
        if (!cliente) { alert("Digite o nome do cliente!"); return; }

        loadingOverlay.classList.add("show");

        fetch(`/olt/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ olt: modo.value, cliente: cliente })
        })
        .then(res => res.json())
        .then(data => {
            jsonContainer.innerHTML = "";
            let overlay_flag = 0;

            if (!data || (Array.isArray(data) && data.length === 0)) {
                alert("Erro: Informe um cliente válido!");
                overlay_flag = 1;
            }

            data.forEach(item => {

                const radio = document.createElement('input');
                radio.type = "radio";
                radio.className = "btn-check";
                radio.autocomplete = "off";
                radio.id = item.olt_ip + ',' + item.fsp + ' ' + item.ont_id;
                radio.name = "onu";

                const label = document.createElement("label");
                label.className = "btn json-card";
                label.setAttribute('for', item.olt_ip + ',' + item.fsp + ' ' + item.ont_id);
                console.log(data);
                if (item.run_state === "online") label.classList.add('online');
                else if (item.run_state === "offline") label.classList.add('offline');
                else label.classList.add('other');

                if (item.alarm === "The dying-gasp of GPON ONTi (DGi) is generated") item.alarm = "Falta de energia";
                else if (item.alarm?.includes("distribute fiber is broken")) item.alarm = "LOSS";
                else if (item.alarm?.includes("loss of GEM")) item.alarm = "LOSS";

                label.innerHTML = `
                    <p><strong>${item.description}</strong></p>
                    <p><strong>FSP:</strong> ${item.fsp}</p>
                    <p><strong>ONU ID:</strong> ${item.ont_id}</p>
                    <p><strong>Status:</strong> ${item.run_state}</p>
                    <p><strong>RX Power:</strong> ${item.rx_power ?? 'N/A'}</p>
                    <p><strong>Last Down:</strong> ${item.alarm ?? 'N/A'}</p>
                    <p><strong>SN:</strong> ${item.sn}</p>
                `;
                jsonContainer.appendChild(radio);
                jsonContainer.appendChild(label);
            });
            
            if (overlay_flag === 0) jsonOverlay.classList.add('show');
        })
        .catch(err => {
            console.error(err);
            alert("Erro ao buscar o status da ONU!");
        })
        .finally(() => loadingOverlay.classList.remove("show"));
    });

    closeJson.addEventListener('click', () => {
        jsonOverlay.classList.remove('show');
    });

    unlockedBtn.addEventListener('click', () => {
        // Liberar ONU selecionada.
        loadingOverlay.classList.add('show');
        const onu = document.querySelector('input[name="onu"]:checked');
        if (!onu) { alert("Selecione uma ONU!"); return; }
        fetch(`/olt/unlocked/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ onu: onu.id })
        })
        .then(res => res.json())
        .then(data => {
            console.log(data);
            if (data.status === "ok"){
		alert("Liberação da ONU foi realizada."); 
		loadingOverlay.classList.remove('show');
		return;}
            else{
                alert("Erro: "+ data.mensagem);
                loadingOverlay.classList.remove('show');
		return;
            }
        })
        .catch(err => console.error(err));
    });
});
