import requests
import pandas as pd
from datetime import datetime, timedelta
import time
from IPython.display import display
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

data_final = datetime.now()
data_inicial = data_final - timedelta(days=10)
datas_extracao = [
    (data_inicial + timedelta(days=i)).strftime("%Y%m%d")
    for i in range((data_final - data_inicial).days + 1)
]

todas_as_licitacoes = []

print(f"Iniciando extração para Minas Gerais (Datas: {datas_extracao[0]} a {datas_extracao[-1]})...\n")

for data_alvo in datas_extracao:
    print(f"--- Buscando dados do dia {data_alvo} ---")
    
    pagina_atual = 1
    total_paginas = 1 
    tentativas_erro_429 = 0 # Contador para gerenciar os bloqueios do servidor
    
    while pagina_atual <= total_paginas:
        parametros = {
            "dataInicial": data_alvo,
            "dataFinal": data_alvo,
            # "codigoModalidadeContratacao": 8,
            "uf": "MG",           
            "pagina": pagina_atual
        }
        
        try:
            resposta = requests.get(url, params=parametros, headers=headers, timeout=30, verify=False)
            
            if resposta.status_code == 200:
                json_resposta = resposta.json()
                
                dados_pagina = json_resposta.get('data', [])
                todas_as_licitacoes.extend(dados_pagina)
                
                total_paginas = json_resposta.get('totalPaginas', 1)
                print(f"  Página {pagina_atual} de {total_paginas} extraída.")
                
                pagina_atual += 1
                tentativas_erro_429 = 0 # Zera o contador de erros após um sucesso
                
                # Pausa de 2 segundos entre as requisições normais
                time.sleep(2) 
                
            elif resposta.status_code == 204:
                print("  Status 204: Nenhuma licitação publicada neste dia.")
                break
                
            elif resposta.status_code == 429:
                tentativas_erro_429 += 1
                tempo_espera = 15 * tentativas_erro_429 # Aguarda 15s na tentativa 1, 30s na tentativa 2...
                
                print(f"  [Alerta] Rate Limit atingido (Erro 429). Aguardando {tempo_espera}s para tentar a página {pagina_atual} novamente...")
                time.sleep(tempo_espera)
                
                if tentativas_erro_429 > 4:
                    print("  Múltiplos bloqueios seguidos. Abortando a extração deste dia para não ter o IP banido.")
                    break
                
            else:
                print(f"  Erro {resposta.status_code} na página {pagina_atual}. Motivo: {resposta.text}")
                break 
                
        except requests.exceptions.RequestException as e:
            print(f"  Falha de conexão na página {pagina_atual}. O servidor pode ter oscilado.")
            break 

if todas_as_licitacoes:
    df_completo = pd.DataFrame(todas_as_licitacoes)
    agora = pd.Timestamp.now()
    
    if 'dataEncerramentoProposta' in df_completo.columns:
        df_completo['dataEncerramentoProposta'] = pd.to_datetime(df_completo['dataEncerramentoProposta'], errors='coerce')
        df_abertos = df_completo[df_completo['dataEncerramentoProposta'] > agora].copy()
    else:
        print("\n[Aviso] A coluna 'dataEncerramentoProposta' não foi localizada.")
        df_abertos = df_completo.copy()
        
    if 'unidadeOrgao' in df_abertos.columns:
        df_abertos['Estado'] = df_abertos['unidadeOrgao'].apply(lambda x: x.get('ufNome') if isinstance(x, dict) else None)
    
    print("\n=== RESUMO DA EXTRAÇÃO MINAS GERAIS ===")
    print(f"Total de registros brutos extraídos: {len(df_completo)}")
    print(f"Total de registros com propostas ABERTAS: {len(df_abertos)}")
    
    df_abertos.to_csv('busca_api_mg_abertos.csv', index=False, sep=';', encoding='utf-8-sig')
    print("Arquivo 'busca_api_mg_abertos.csv' gerado com sucesso!")
    
    colunas_para_exibir = [c for c in ['orgaoEntidade', 'numeroControlePNCP', 'Estado', 'dataEncerramentoProposta'] if c in df_abertos.columns]
    display(df_abertos[colunas_para_exibir].head())
else:
    print("\nNenhum dado foi extraído no total.")