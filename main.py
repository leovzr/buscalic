import ast
import io
import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Licitações MG - PNCP",
    page_icon="📊",
    layout="wide",
)

ID_ARQUIVO_DRIVE = "1xDcf-GopNrTl0psHCsY_v-0E7B91XM57"

COLUNAS_EXIBICAO = [
    "orgaoEntidade.razaoSocial",
    "unidadeOrgao.municipioNome",
    "modalidadeNome",
    "srp",
    "objetoCompra",
    "dataEncerramentoProposta",
    "valorTotalEstimado",
    "linkSistemaOrigem",
]


def interpretar_dicionario(valor):
    if pd.isna(valor):
        return {}
    if isinstance(valor, dict):
        return valor
    if isinstance(valor, str):
        try:
            return ast.literal_eval(valor)
        except (ValueError, SyntaxError):
            return {}
    return {}


@st.cache_data(ttl=600, show_spinner="Baixando dados do Google Drive...")
def carregar_dados_drive(file_id: str) -> pd.DataFrame:
    # Lê as credenciais diretamente do arquivo .streamlit/secrets.toml
    credenciais_info = dict(st.secrets["gcp_service_account"])
    credenciais_info["private_key"] = credenciais_info["private_key"].replace("\\n", "\n")

    credenciais = service_account.Credentials.from_service_account_info(
        credenciais_info,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    servico_drive = build("drive", "v3", credentials=credenciais)

    # Faz o download do CSV direto para a memória (sem precisar salvar arquivo local)
    requisicao = servico_drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, requisicao)

    concluido = False
    while not concluido:
        _, concluido = downloader.next_chunk()

    buffer.seek(0)
    df = pd.read_csv(buffer, sep=";", encoding="utf-8-sig")

    # Descompacta orgaoEntidade.razaoSocial caso ainda esteja como dicionário
    if "orgaoEntidade.razaoSocial" not in df.columns and "orgaoEntidade" in df.columns:
        orgao_dicts = df["orgaoEntidade"].apply(interpretar_dicionario)
        df["orgaoEntidade.razaoSocial"] = orgao_dicts.apply(
            lambda x: x.get("razaoSocial", x.get("razaosocial")) if isinstance(x, dict) else None
        )

    # Descompacta unidadeOrgao.municipioNome caso ainda esteja como dicionário
    if "unidadeOrgao.municipioNome" not in df.columns and "unidadeOrgao" in df.columns:
        unidade_dicts = df["unidadeOrgao"].apply(interpretar_dicionario)
        df["unidadeOrgao.municipioNome"] = unidade_dicts.apply(
            lambda x: x.get("municipioNome") if isinstance(x, dict) else None
        )

    # Garante a tipagem correta para ordenação e formatação na tabela
    if "dataEncerramentoProposta" in df.columns:
        df["dataEncerramentoProposta"] = pd.to_datetime(
            df["dataEncerramentoProposta"], errors="coerce"
        )

    if "valorTotalEstimado" in df.columns:
        df["valorTotalEstimado"] = pd.to_numeric(
            df["valorTotalEstimado"], errors="coerce"
        )

    return df


# --- INTERFACE PRINCIPAL ---
col_titulo, col_botao = st.columns([5, 1])
with col_titulo:
    st.title("Licitações em Aberto - Minas Gerais (PNCP)")
with col_botao:
    st.write("")  # Alinhamento vertical com o título
    if st.button("🔄 Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

try:
    df = carregar_dados_drive(ID_ARQUIVO_DRIVE)
except Exception as erro:
    st.error(f"Erro ao carregar os dados do Google Drive: {erro}")
    st.stop()

# Garante que todas as colunas solicitadas existam antes de filtrar/exibir
colunas_faltantes = [c for c in COLUNAS_EXIBICAO if c not in df.columns]
if colunas_faltantes:
    st.warning(f"Algumas colunas não foram encontradas no CSV: {colunas_faltantes}")

# --- FILTROS (ANTES DA TABELA) ---
col_filtro1, col_filtro2 = st.columns(2)

with col_filtro1:
    opcoes_modalidade = sorted(df["modalidadeNome"].dropna().unique()) if "modalidadeNome" in df.columns else []
    modalidades_sel = st.multiselect(
        "Modalidade (`modalidadeNome`)",
        options=opcoes_modalidade,
        placeholder="Todas as modalidades",
    )

with col_filtro2:
    opcoes_municipio = sorted(df["unidadeOrgao.municipioNome"].dropna().unique()) if "unidadeOrgao.municipioNome" in df.columns else []
    municipios_sel = st.multiselect(
        "Município (`unidadeOrgao.municipioNome`)",
        options=opcoes_municipio,
        placeholder="Todos os municípios",
    )

# Aplicação dos filtros
df_filtrado = df.copy()
if modalidades_sel:
    df_filtrado = df_filtrado[df_filtrado["modalidadeNome"].isin(modalidades_sel)]
if municipios_sel:
    df_filtrado = df_filtrado[df_filtrado["unidadeOrgao.municipioNome"].isin(municipios_sel)]

# --- TABELA DE DADOS ---
colunas_disponiveis = [c for c in COLUNAS_EXIBICAO if c in df_filtrado.columns]
st.caption(f"Exibindo **{len(df_filtrado)}** de **{len(df)}** registros.")

st.dataframe(
    df_filtrado[colunas_disponiveis],
    use_container_width=True,
    hide_index=True,
    column_config={
        "orgaoEntidade.razaoSocial": st.column_config.TextColumn("Órgão / Entidade"),
        "unidadeOrgao.municipioNome": st.column_config.TextColumn("Município"),
        "modalidadeNome": st.column_config.TextColumn("Modalidade"),
        "srp": st.column_config.CheckboxColumn("SRP"),
        "objetoCompra": st.column_config.TextColumn("Objeto da Compra"),
        "dataEncerramentoProposta": st.column_config.DatetimeColumn(
            "Encerramento da Proposta",
            format="DD/MM/YYYY HH:mm",
        ),
        "valorTotalEstimado": st.column_config.NumberColumn(
            "Valor Total Estimado",
            format="R$ %.2f",
        ),
        "linkSistemaOrigem": st.column_config.LinkColumn(
            "Link de Origem",
            display_text="Abrir edital",
        ),
    },
)