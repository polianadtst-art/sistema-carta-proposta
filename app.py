# ============================================================================
# ARQUIVO: app.py (Versão 2.0 — Regularize Assessoria Rural)
# O QUE ESTE ARQUIVO FAZ:
#   Sistema web multiusuário em Português do Brasil (PT-BR) conectado ao
#   PostgreSQL (Supabase), com:
#   - Busca de CEP corrigida (ViaCEP + BrasilAPI + OpenCEP) puxando Rua/Bairro/Cidade/UF
#   - Formatação automática de CPF (000.000.000-00) e CNPJ (00.000.000/0000-00)
#   - Carência com opção de 1 ano, 2 anos e 3 anos
#   - Principais culturas de Minas Gerais
#   - Linhas de crédito com filtro automático de itens financiáveis e descrições completas
#   - Margem de Crédito Pessoal e Avalistas em blocos separados + Parecer da Agência
#   - Ordem de Serviço exibindo Valor Cheio (2,00%) e Desconto Concedido da Faixa
#   - Impressão 100% em Preto e Branco, 1 folha A4 por documento e marca d'água Regularize
#
#   Você NÃO precisa mexer neste arquivo!
#   - Para alterar dados da empresa/taxas/culturas/linhas: edite config.py
#   - Para alterar senha do banco ou usuários: edite Settings -> Secrets no Streamlit
# ============================================================================

import io
import json
import re
import urllib.request
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from config import (
    BANCOS_PADRAO,
    CARENCIAS_PADRAO,
    CATALOGO_SERVICOS,
    CULTURAS_MG,
    DOCS_COOBRIGADOS,
    DOCS_IMOVEL,
    DOCS_PROPONENTE,
    DOCUMENTOS_CLIENTE_PADRAO,
    EMPRESA,
    FAIXAS_HONORARIOS,
    PACOTES_BANCOS,
    TAXA_HONORARIO_CHEIA,
    TIPOS_CLIENTE_PADRAO,
    TIPOS_CREDITO_PESSOAL_PADRAO,
    TIPOS_ENVIO_PADRAO,
    TODOS_OS_DOCUMENTOS,
)
from pdf_generator import fmt_cep, fmt_doc, fmt_moeda, gerar_pdf_bytes

# ============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA (PORTUGUÊS DO BRASIL)
# ============================================================================
st.set_page_config(
    page_title=f"Sistema Carta-Proposta | {EMPRESA['nome_fantasia']}",
    page_icon="🌱",
    layout="wide",
)


# ============================================================================
# 2. CONEXÃO SEGURA COM O POSTGRESQL (SUPABASE) E ATUALIZAÇÃO AUTOMÁTICA
# ============================================================================
@st.cache_resource
def conectar_banco():
    """Conecta ao PostgreSQL usando a variável DATABASE_URL salva nos Secrets."""
    if "DATABASE_URL" not in st.secrets:
        st.error(
            "❌ Configuração pendente: 'DATABASE_URL' não foi encontrada nos Segredos (Secrets).\n"
            "Acesse Gerenciar aplicativo -> Configurações -> Segredos e cole o link do Supabase."
        )
        st.stop()

    url = st.secrets["DATABASE_URL"]
    # Garante uso do driver psycopg (versão 3) compatível com Python 3.12 / 3.13 / 3.14
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    eng = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    # Atualiza silenciosamente colunas novas no banco existente (sem risco aos dados antigos!)
    try:
        with eng.begin() as conn:
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS parecer_agencia TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS valor_cheio_os NUMERIC(15,2) DEFAULT 0"))
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS desconto_faixa NUMERIC(15,2) DEFAULT 0"))
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS desconto_extra NUMERIC(15,2) DEFAULT 0"))
            conn.execute(text(
                "INSERT INTO aux_listas_gerais (categoria, valor) VALUES ('CARENCIA', 'SIM (1 ano)') "
                "ON CONFLICT (categoria, valor) DO NOTHING"
            ))
    except Exception:
        # Se as tabelas ainda não foram criadas, o erro aparecerá de forma clara adiante
        pass

    return eng


engine = conectar_banco()


# ============================================================================
# 3. TELA DE LOGIN (CONTROLE DE ACESSO MULTIUSUÁRIO)
# ============================================================================
def verificar_login():
    """Exibe a tela de login protegida por usuário e senha."""
    if st.session_state.get("usuario_logado"):
        return st.session_state["usuario_logado"]

    st.markdown(f"## 🌱 {EMPRESA['nome_fantasia']}")
    st.caption("Sistema Web de Carta-Proposta, Análise Produtiva e Ordem de Serviço")

    col_e, col_m, col_d = st.columns([1, 1.5, 1])
    with col_m:
        with st.form("form_login"):
            st.subheader("Acesso Restrito à Equipe")
            email = st.text_input("E-mail de acesso").strip().lower()
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar no Sistema", use_container_width=True)

            if entrar:
                usuarios_permitidos = dict(st.secrets.get("usuarios", {}))
                mapa_lower = {k.strip().lower(): str(v) for k, v in usuarios_permitidos.items()}
                if email in mapa_lower and senha == mapa_lower[email]:
                    st.session_state["usuario_logado"] = email
                    st.rerun()
                else:
                    st.error("E-mail ou senha incorretos. Verifique com a administração.")
    st.stop()


usuario_atual = verificar_login()


# ============================================================================
# 4. FUNÇÕES AUXILIARES (CPF/CNPJ, CEP MULTI-PROVEDOR E BANCO)
# ============================================================================
def apenas_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def normalizar_espacos(texto):
    return re.sub(r"\s+", " ", str(texto or "").strip())


def buscar_cep_online(cep_texto):
    """
    Consulta o CEP em até 3 serviços gratuitos brasileiros (ViaCEP -> BrasilAPI -> OpenCEP).
    Retorna dicionário padronizado {'rua', 'bairro', 'cidade', 'uf', 'cep'} ou None.
    """
    dig = apenas_digitos(cep_texto)
    if len(dig) != 8:
        return None

    headers = {"User-Agent": "Mozilla/5.0 (SistemaRegularize/2.0)"}

    # 1. Tentativa: ViaCEP (mais completo para logradouros dos Correios)
    try:
        req = urllib.request.Request(f"https://viacep.com.br/ws/{dig}/json/", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            if not d.get("erro"):
                return {
                    "cep": fmt_cep(dig),
                    "rua": (d.get("logradouro") or "").strip(),
                    "bairro": (d.get("bairro") or "").strip(),
                    "cidade": (d.get("localidade") or "").strip(),
                    "uf": (d.get("uf") or "").strip().upper(),
                }
    except Exception:
        pass

    # 2. Tentativa (fallback): BrasilAPI v2
    try:
        req = urllib.request.Request(f"https://brasilapi.com.br/api/cep/v2/{dig}", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            if d.get("city"):
                return {
                    "cep": fmt_cep(dig),
                    "rua": (d.get("street") or "").strip(),
                    "bairro": (d.get("neighborhood") or "").strip(),
                    "cidade": (d.get("city") or "").strip(),
                    "uf": (d.get("state") or "").strip().upper(),
                }
    except Exception:
        pass

    # 3. Tentativa (fallback): OpenCEP
    try:
        req = urllib.request.Request(f"https://opencep.com/v1/{dig}.json", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            if d.get("localidade"):
                return {
                    "cep": fmt_cep(dig),
                    "rua": (d.get("logradouro") or "").strip(),
                    "bairro": (d.get("bairro") or "").strip(),
                    "cidade": (d.get("localidade") or "").strip(),
                    "uf": (d.get("uf") or "").strip().upper(),
                }
    except Exception:
        pass

    return None


@st.cache_data(ttl=60)
def carregar_listas_auxiliares():
    """Carrega contabilidades e listas complementares do PostgreSQL combinadas com o catálogo atualizado."""
    with engine.connect() as conn:
        df_serv = pd.read_sql(
            text("SELECT linha_credito, tipo_servico, descricao_servico FROM aux_servicos ORDER BY tipo_servico"),
            conn,
        )
        df_listas = pd.read_sql(
            text("SELECT categoria, valor FROM aux_listas_gerais ORDER BY categoria, valor"),
            conn,
        )
        df_cont = pd.read_sql(
            text("SELECT id, nome, COALESCE(cnpj, '') AS cnpj FROM contabilidades ORDER BY nome"),
            conn,
        )

    listas_db = {}
    for cat, grupo in df_listas.groupby("categoria"):
        listas_db[cat] = [normalizar_espacos(v) for v in grupo["valor"].tolist() if str(v).strip()]

    # Mescla catálogo profissional (config.py) com eventuais serviços extras do banco
    catalogo_completo = {k: dict(v) for k, v in CATALOGO_SERVICOS.items()}
    for _, r in df_serv.iterrows():
        s = normalizar_espacos(r["tipo_servico"])
        if s and s not in catalogo_completo:
            # Verifica se existe equivalente próximo já no catálogo novo
            catalogo_completo[s] = {
                "linha": normalizar_espacos(r["linha_credito"] or "OUTROS"),
                "descricao": str(r["descricao_servico"] or ""),
                "itens": listas_db.get("ITEM", []),
            }

    # Monta listas finais sem duplicidades
    def _unir(padrao, extras):
        vistos = set()
        saida = []
        for x in list(padrao) + list(extras):
            xn = normalizar_espacos(x)
            if xn and xn.upper() not in vistos:
                vistos.add(xn.upper())
                saida.append(xn)
        return saida

    listas_finais = {
        "CARENCIA": _unir(CARENCIAS_PADRAO, listas_db.get("CARENCIA", [])),
        "CULTURA": _unir(CULTURAS_MG, listas_db.get("CULTURA", [])),
        "BANCO": _unir(BANCOS_PADRAO, listas_db.get("BANCO", [])),
        "TIPO_CLIENTE": _unir(TIPOS_CLIENTE_PADRAO, listas_db.get("TIPO_CLIENTE", [])),
        "TIPO_CREDITO": _unir(TIPOS_CREDITO_PESSOAL_PADRAO, listas_db.get("TIPO_CREDITO", [])),
        "TIPO_ENVIO": _unir(TIPOS_ENVIO_PADRAO, listas_db.get("TIPO_ENVIO", [])),
        "TODOS_ITENS": _unir(
            [it for v in CATALOGO_SERVICOS.values() for it in v["itens"]],
            listas_db.get("ITEM", []),
        ),
    }
    return catalogo_completo, listas_finais, df_cont


def _propriedade_vazia():
    return {
        "nome": "", "matricula": "", "num_pes": 0, "espacamento": "",
        "variedades": "", "idade": "", "prev_2027": "",
        "prod_2026": "", "prod_2025": "", "prod_2024": "",
        "venda_2026": 0.0, "venda_2025": 0.0, "venda_2024": 0.0,
    }


def inicializar_estado_proposta():
    """Inicializa os campos isolados na sessão do usuário atual."""
    primeiro_serv = "PRONAF - CUSTEIO AGRÍCOLA"
    padrao = {
        "proposta_id_edicao": None,
        "local_emissao": EMPRESA["cidade_padrao"],
        "data_proposta": date.today(),
        "parceiro": EMPRESA["nome_fantasia"],
        "banco_destino": "BANCO DO BRASIL",
        "cliente_cpf": "",
        "cliente_nome": "",
        "cliente_telefone": "",
        "tipo_cliente": "PROPRIETÁRIO",
        "cep": "",
        "rua": "",
        "localidade": "",
        "bairro": "",
        "cidade": EMPRESA["cidade_padrao"],
        "uf": EMPRESA["uf_padrao"],
        "aviso_cep": "",
        "contabilidade_nome": "",
        "contabilidade_cnpj": "",
        "imovel_beneficiado_texto": "",
        "filtro_linha_credito": "TODAS AS LINHAS",
        "tipo_servico": primeiro_serv,
        "descricao_servico": CATALOGO_SERVICOS[primeiro_serv]["descricao"],
        "item_financiado": CATALOGO_SERVICOS[primeiro_serv]["itens"][0],
        "item_financiado_custom": "",
        "cultura": "CAFÉ ARÁBICA",
        "carencia": "Não",
        "valor_proposto": 0.0,
        "tipo_envio_docs": "DIGITAL/E-MAIL",
        "data_envio_docs": "",
        "faixa_honorario_idx": 2,
        "desconto_extra": 0.0,
        "acrescimos": 0.0,
        "forma_pagamento": "Na emissão da minuta",
        "num_parcelas": 1,
        "avalista_nome": "",
        "avalista_cpf": "",
        "conjuge_avalista_nome": "",
        "conjuge_avalista_cpf": "",
        "credito_tipo": "",
        "credito_valor": 0.0,
        "beneficio_valor": 0.0,
        "parcela_consorcio": 0.0,
        "num_parcelas_consorcio": 0,
        "parecer_agencia": "",
        "checklist_docs": {},
        "propriedades_lista": [_propriedade_vazia()],
        "semoventes": {
            "vacas_leite": 0, "litros_dia": 0.0, "preco_litro": 0.0,
            "boi_corte": 0, "novilhas": 0, "bezerros": 0,
        },
        "renda_extra_1_desc": "",
        "renda_extra_1_val": 0.0,
        "renda_extra_2_desc": "",
        "renda_extra_2_val": 0.0,
        "bens": "",
    }
    for k, v in padrao.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================================
# 5. CALLBACKS (GARANTEM ATUALIZAÇÃO IMEDIATA DOS CAMPOS NA TELA SEM BUGS)
# ============================================================================
def cb_formatar_doc(chave_campo):
    """Formata automaticamente CPF (000.000.000-00) ou CNPJ (00.000.000/0000-00)."""
    atual = st.session_state.get(chave_campo, "")
    st.session_state[chave_campo] = fmt_doc(atual)


def cb_buscar_cep():
    """
    CORREÇÃO DO ITEM 14:
    Roda ANTES dos campos serem redesenhados na tela, garantindo que Rua, Bairro,
    Cidade e UF sejam preenchidos imediatamente nos respectivos inputs!
    """
    cep_digitado = st.session_state.get("cep", "")
    dig = apenas_digitos(cep_digitado)
    if len(dig) != 8:
        st.session_state["aviso_cep"] = "erro:Digite um CEP válido com 8 números (ex.: 31920-350)."
        return

    st.session_state["cep"] = fmt_cep(dig)
    res = buscar_cep_online(dig)
    if not res:
        st.session_state["aviso_cep"] = "erro:CEP não encontrado nos Correios. Confira os números ou preencha o endereço manualmente."
        return

    st.session_state["cidade"] = res["cidade"] or st.session_state.get("cidade", "")
    st.session_state["uf"] = res["uf"] or st.session_state.get("uf", "MG")
    st.session_state["bairro"] = res["bairro"]
    st.session_state["rua"] = res["rua"]

    if res["rua"]:
        st.session_state["aviso_cep"] = f"ok:Endereço encontrado: {res['rua']} — {res['bairro']} ({res['cidade']}/{res['uf']})."
    else:
        st.session_state["aviso_cep"] = (
            f"info:CEP geral do município ({res['cidade']}/{res['uf']}). Os Correios não vinculam nome de rua a CEPs únicos de cidade — digite a rua ou localidade manualmente."
        )


def cb_limpar_formulario():
    chaves_manter = {"usuario_logado"}
    for k in list(st.session_state.keys()):
        if k not in chaves_manter:
            del st.session_state[k]
    inicializar_estado_proposta()


def cb_ao_trocar_servico(catalogo):
    """Atualiza automaticamente a Descrição do Serviço e sugere o 1º item daquela linha."""
    serv = st.session_state.get("tipo_servico", "")
    info = catalogo.get(serv)
    if info:
        st.session_state["descricao_servico"] = info.get("descricao", "")
        itens_linha = info.get("itens", [])
        if itens_linha and st.session_state.get("item_financiado") not in itens_linha:
            st.session_state["item_financiado"] = itens_linha[0]


def cb_aplicar_imovel_salvo():
    esc = st.session_state.get("seletor_imovel_salvo", "(Manter digitado)")
    if esc and esc != "(Manter digitado)":
        st.session_state["imovel_beneficiado_texto"] = esc


def cb_carregar_cliente(cpf_cnpj):
    """Carrega cliente + propriedades + contabilidade do PostgreSQL antes da renderização."""
    with engine.connect() as conn:
        cli = conn.execute(
            text("""
                SELECT c.*, ct.nome AS cont_nome, COALESCE(ct.cnpj, '') AS cont_cnpj
                FROM clientes c
                LEFT JOIN contabilidades ct ON ct.id = c.contabilidade_id
                WHERE c.cpf_cnpj = :cpf
            """),
            {"cpf": cpf_cnpj},
        ).mappings().first()

        if not cli:
            return

        props = conn.execute(
            text("""
                SELECT nome_propriedade, COALESCE(matricula, '') AS matricula,
                       COALESCE(num_pes_cafe, 0) AS num_pes,
                       COALESCE(espacamento, '') AS espacamento,
                       COALESCE(variedades, '') AS variedades,
                       COALESCE(idade_lavoura, '') AS idade
                FROM propriedades
                WHERE cliente_cpf_cnpj = :cpf
                ORDER BY id
            """),
            {"cpf": cpf_cnpj},
        ).mappings().all()

    st.session_state["cliente_cpf"] = fmt_doc(cli["cpf_cnpj"])
    st.session_state["cliente_nome"] = cli["nome"] or ""
    st.session_state["cliente_telefone"] = cli["telefone"] or ""
    st.session_state["tipo_cliente"] = cli["tipo_cliente"] or "PROPRIETÁRIO"
    st.session_state["cep"] = fmt_cep(cli["cep"] or "")
    st.session_state["rua"] = cli["rua"] or ""
    st.session_state["localidade"] = cli["localidade"] or ""
    st.session_state["bairro"] = cli["bairro"] or ""
    st.session_state["cidade"] = cli["cidade"] or EMPRESA["cidade_padrao"]
    st.session_state["uf"] = cli["uf"] or EMPRESA["uf_padrao"]
    st.session_state["contabilidade_nome"] = cli["cont_nome"] or ""
    st.session_state["contabilidade_cnpj"] = fmt_doc(cli["cont_cnpj"] or "")

    if props:
        lista_p = []
        for p in props:
            item_p = _propriedade_vazia()
            item_p.update({
                "nome": p["nome_propriedade"],
                "matricula": p["matricula"],
                "num_pes": int(p["num_pes"] or 0),
                "espacamento": p["espacamento"],
                "variedades": p["variedades"],
                "idade": p["idade"],
            })
            lista_p.append(item_p)
        st.session_state["propriedades_lista"] = lista_p
        p0 = lista_p[0]
        st.session_state["imovel_beneficiado_texto"] = (
            f"{p0['nome']} Mat {p0['matricula']}".strip() if p0["matricula"] else p0["nome"]
        )
    else:
        st.session_state["propriedades_lista"] = [_propriedade_vazia()]
    st.session_state["aviso_cep"] = ""


def cb_carregar_proposta(proposta_id):
    """Carrega uma proposta salva do histórico para edição ou reimpressão."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM propostas WHERE id = :pid"),
            {"pid": int(proposta_id)},
        ).mappings().first()

    if not row:
        return

    cb_carregar_cliente(row["cliente_cpf_cnpj"])
    st.session_state["proposta_id_edicao"] = row["id"]
    st.session_state["data_proposta"] = row["data_proposta"] or date.today()
    st.session_state["local_emissao"] = row["local_emissao"] or EMPRESA["cidade_padrao"]
    st.session_state["parceiro"] = row["parceiro"] or EMPRESA["nome_fantasia"]
    st.session_state["banco_destino"] = row["banco_destino"] or "BANCO DO BRASIL"
    st.session_state["imovel_beneficiado_texto"] = row["imovel_beneficiado_texto"] or ""
    st.session_state["filtro_linha_credito"] = "TODAS AS LINHAS"
    st.session_state["tipo_servico"] = row["tipo_servico"] or "PRONAF - CUSTEIO AGRÍCOLA"
    st.session_state["descricao_servico"] = row["descricao_servico"] or ""
    st.session_state["item_financiado"] = row["item_financiado"] or ""
    st.session_state["cultura"] = row["cultura"] or "CAFÉ ARÁBICA"
    st.session_state["carencia"] = normalizar_espacos(row["carencia"] or "Não")
    st.session_state["valor_proposto"] = float(row["valor_proposto"] or 0)
    st.session_state["tipo_envio_docs"] = row["tipo_envio_docs"] or "DIGITAL/E-MAIL"
    st.session_state["data_envio_docs"] = row["data_envio_docs"] or ""
    st.session_state["faixa_honorario_idx"] = int(row["faixa_honorario_idx"] or 2)
    st.session_state["desconto_extra"] = float(row.get("desconto_extra") or 0)
    st.session_state["acrescimos"] = float(row["acrescimos"] or 0)
    st.session_state["forma_pagamento"] = row["forma_pagamento"] or "Na emissão da minuta"
    st.session_state["num_parcelas"] = max(1, int(row["num_parcelas"] or 1))
    st.session_state["avalista_nome"] = row["avalista_nome"] or ""
    st.session_state["avalista_cpf"] = fmt_doc(row["avalista_cpf"] or "")
    st.session_state["conjuge_avalista_nome"] = row["conjuge_avalista_nome"] or ""
    st.session_state["conjuge_avalista_cpf"] = fmt_doc(row["conjuge_avalista_cpf"] or "")
    st.session_state["credito_tipo"] = row["credito_tipo"] or ""
    st.session_state["credito_valor"] = float(row["credito_valor"] or 0)
    st.session_state["beneficio_valor"] = float(row["beneficio_valor"] or 0)
    st.session_state["parcela_consorcio"] = float(row["parcela_consorcio"] or 0)
    st.session_state["num_parcelas_consorcio"] = int(row["num_parcelas_consorcio"] or 0)
    st.session_state["parecer_agencia"] = row.get("parecer_agencia") or ""
    st.session_state["checklist_docs"] = dict(row["checklist_docs"] or {})

    prod = dict(row["dados_producao"] or {})
    if prod.get("propriedades"):
        st.session_state["propriedades_lista"] = prod["propriedades"]
    if prod.get("semoventes"):
        st.session_state["semoventes"] = prod["semoventes"]
    st.session_state["renda_extra_1_desc"] = prod.get("renda_extra_1_desc", "")
    st.session_state["renda_extra_1_val"] = float(prod.get("renda_extra_1_val") or 0)
    st.session_state["renda_extra_2_desc"] = prod.get("renda_extra_2_desc", "")
    st.session_state["renda_extra_2_val"] = float(prod.get("renda_extra_2_val") or 0)
    st.session_state["bens"] = prod.get("bens", "")


# ============================================================================
# 6. CÁLCULOS FINANCEIROS (REGRA DO ITEM 7: VALOR CHEIO 2% + DESCONTO DA FAIXA)
# ============================================================================
def montar_dicionario_proposta():
    """Calcula Honorários Cheios (2,00%), Desconto da Faixa, Total OS e Renda Bruta."""
    idx_faixa = int(st.session_state.get("faixa_honorario_idx", 2))
    info_faixa = FAIXAS_HONORARIOS.get(idx_faixa, FAIXAS_HONORARIOS[2])
    pct_final = float(info_faixa["percentual"])
    pct_desc_faixa = max(0.0, round(TAXA_HONORARIO_CHEIA - pct_final, 6))

    val_prop = float(st.session_state.get("valor_proposto") or 0.0)
    # Valor Cheio sempre sobre 2,00%
    valor_cheio_os = round(val_prop * TAXA_HONORARIO_CHEIA, 2)
    # Desconto concedido automaticamente pela faixa de honorários escolhida
    desconto_faixa = round(val_prop * pct_desc_faixa, 2)
    # Desconto extra opcional digitado manualmente
    desconto_extra = float(st.session_state.get("desconto_extra") or 0.0)
    desconto_total = round(desconto_faixa + desconto_extra, 2)
    acresc = float(st.session_state.get("acrescimos") or 0.0)

    total_os = max(0.0, round(valor_cheio_os - desconto_total + acresc, 2))
    n_parc = max(1, int(st.session_state.get("num_parcelas") or 1))
    val_parc = round(total_os / n_parc, 2)

    props = st.session_state.get("propriedades_lista") or []
    soma_vendas = sum(float(p.get("venda_2026") or 0) for p in props)
    renda_bruta = round(
        soma_vendas
        + float(st.session_state.get("renda_extra_1_val") or 0)
        + float(st.session_state.get("renda_extra_2_val") or 0),
        2,
    )

    item_sel = st.session_state.get("item_financiado", "")
    if item_sel == "OUTRO ITEM (DIGITAR MANUALMENTE)":
        item_final = st.session_state.get("item_financiado_custom", "").strip().upper()
    else:
        item_final = item_sel

    return {
        "local_emissao": st.session_state["local_emissao"],
        "data_proposta": st.session_state["data_proposta"],
        "parceiro": st.session_state["parceiro"],
        "banco_destino": st.session_state["banco_destino"],
        "cliente_cpf": apenas_digitos(st.session_state["cliente_cpf"]),
        "cliente_nome": st.session_state["cliente_nome"].strip().upper(),
        "cliente_telefone": st.session_state["cliente_telefone"],
        "tipo_cliente": st.session_state["tipo_cliente"],
        "cep": fmt_cep(st.session_state["cep"]),
        "rua": st.session_state["rua"].strip(),
        "localidade": st.session_state["localidade"].strip(),
        "bairro": st.session_state["bairro"].strip(),
        "cidade": st.session_state["cidade"].strip(),
        "uf": st.session_state["uf"].strip().upper()[:2],
        "contabilidade_nome": st.session_state["contabilidade_nome"],
        "contabilidade_cnpj": st.session_state["contabilidade_cnpj"],
        "imovel_beneficiado_texto": st.session_state["imovel_beneficiado_texto"].strip(),
        "tipo_servico": st.session_state["tipo_servico"],
        "descricao_servico": st.session_state["descricao_servico"].strip(),
        "item_financiado": item_final,
        "cultura": st.session_state["cultura"],
        "carencia": st.session_state["carencia"],
        "valor_proposto": val_prop,
        "tipo_envio_docs": st.session_state["tipo_envio_docs"],
        "data_envio_docs": st.session_state["data_envio_docs"],
        "faixa_honorario_idx": idx_faixa,
        "percentual_honorario": pct_final,
        "percentual_desconto_faixa": pct_desc_faixa,
        "valor_cheio_os": valor_cheio_os,
        "valor_projeto_tecnico": valor_cheio_os,
        "desconto_faixa": desconto_faixa,
        "desconto_extra": desconto_extra,
        "desconto": desconto_total,
        "acrescimos": acresc,
        "valor_total_os": total_os,
        "forma_pagamento": st.session_state["forma_pagamento"],
        "num_parcelas": n_parc,
        "valor_parcela": val_parc,
        "avalista_nome": st.session_state["avalista_nome"].strip().upper(),
        "avalista_cpf": apenas_digitos(st.session_state["avalista_cpf"]),
        "conjuge_avalista_nome": st.session_state["conjuge_avalista_nome"].strip().upper(),
        "conjuge_avalista_cpf": apenas_digitos(st.session_state["conjuge_avalista_cpf"]),
        "credito_tipo": st.session_state["credito_tipo"],
        "credito_valor": float(st.session_state.get("credito_valor") or 0),
        "beneficio_valor": float(st.session_state.get("beneficio_valor") or 0),
        "parcela_consorcio": float(st.session_state.get("parcela_consorcio") or 0),
        "num_parcelas_consorcio": int(st.session_state.get("num_parcelas_consorcio") or 0),
        "parecer_agencia": st.session_state.get("parecer_agencia", "").strip(),
        "checklist_docs": st.session_state.get("checklist_docs", {}),
        "dados_producao": {
            "propriedades": props,
            "semoventes": st.session_state.get("semoventes", {}),
            "renda_extra_1_desc": st.session_state.get("renda_extra_1_desc", ""),
            "renda_extra_1_val": float(st.session_state.get("renda_extra_1_val") or 0),
            "renda_extra_2_desc": st.session_state.get("renda_extra_2_desc", ""),
            "renda_extra_2_val": float(st.session_state.get("renda_extra_2_val") or 0),
            "bens": st.session_state.get("bens", ""),
        },
        "renda_bruta_anual": renda_bruta,
    }


def salvar_tudo_no_banco():
    """Salva Cliente, Propriedades e Proposta de forma atômica (seguro para vários usuários ao mesmo tempo)."""
    d = montar_dicionario_proposta()
    if len(d["cliente_cpf"]) not in (11, 14):
        st.error("❌ Informe um CPF (11 números) ou CNPJ (14 números) válido antes de salvar.")
        return None
    if not d["cliente_nome"]:
        st.error("❌ Preencha o Nome Completo do Produtor antes de salvar.")
        return None

    with engine.begin() as conn:
        cont_id = None
        if d["contabilidade_nome"]:
            res_c = conn.execute(
                text("SELECT id FROM contabilidades WHERE nome = :n"),
                {"n": d["contabilidade_nome"]},
            ).first()
            if res_c:
                cont_id = res_c[0]

        conn.execute(
            text("""
                INSERT INTO clientes (
                    cpf_cnpj, nome, telefone, tipo_cliente, cep, rua,
                    localidade, bairro, cidade, uf, contabilidade_id, atualizado_em
                ) VALUES (
                    :cpf, :nome, :tel, :tipo, :cep, :rua,
                    :loc, :bairro, :cid, :uf, :cont_id, NOW()
                )
                ON CONFLICT (cpf_cnpj) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    telefone = EXCLUDED.telefone,
                    tipo_cliente = EXCLUDED.tipo_cliente,
                    cep = EXCLUDED.cep,
                    rua = EXCLUDED.rua,
                    localidade = EXCLUDED.localidade,
                    bairro = EXCLUDED.bairro,
                    cidade = EXCLUDED.cidade,
                    uf = EXCLUDED.uf,
                    contabilidade_id = EXCLUDED.contabilidade_id,
                    atualizado_em = NOW()
            """),
            {
                "cpf": d["cliente_cpf"], "nome": d["cliente_nome"],
                "tel": d["cliente_telefone"], "tipo": d["tipo_cliente"],
                "cep": d["cep"], "rua": d["rua"], "loc": d["localidade"],
                "bairro": d["bairro"], "cid": d["cidade"], "uf": d["uf"],
                "cont_id": cont_id,
            },
        )

        prop_benef_id = None
        for idx, p in enumerate(d["dados_producao"]["propriedades"]):
            nome_p = str(p.get("nome") or "").strip()
            if not nome_p:
                continue
            mat_p = str(p.get("matricula") or "").strip()
            res_p = conn.execute(
                text("""
                    INSERT INTO propriedades (
                        cliente_cpf_cnpj, nome_propriedade, matricula,
                        num_pes_cafe, espacamento, variedades, idade_lavoura, atualizado_em
                    ) VALUES (
                        :cpf, :nome, :mat, :pes, :esp, :var, :idade, NOW()
                    )
                    ON CONFLICT (cliente_cpf_cnpj, nome_propriedade, matricula) DO UPDATE SET
                        num_pes_cafe = EXCLUDED.num_pes_cafe,
                        espacamento = EXCLUDED.espacamento,
                        variedades = EXCLUDED.variedades,
                        idade_lavoura = EXCLUDED.idade_lavoura,
                        atualizado_em = NOW()
                    RETURNING id
                """),
                {
                    "cpf": d["cliente_cpf"], "nome": nome_p, "mat": mat_p,
                    "pes": int(p.get("num_pes") or 0),
                    "esp": str(p.get("espacamento") or ""),
                    "var": str(p.get("variedades") or ""),
                    "idade": str(p.get("idade") or ""),
                },
            ).first()
            if idx == 0 and res_p:
                prop_benef_id = res_p[0]

        params_prop = {
            "data_proposta": d["data_proposta"],
            "local_emissao": d["local_emissao"],
            "parceiro": d["parceiro"],
            "banco_destino": d["banco_destino"],
            "cliente_cpf_cnpj": d["cliente_cpf"],
            "propriedade_beneficiada_id": prop_benef_id,
            "imovel_beneficiado_texto": d["imovel_beneficiado_texto"],
            "tipo_servico": d["tipo_servico"],
            "descricao_servico": d["descricao_servico"],
            "item_financiado": d["item_financiado"],
            "cultura": d["cultura"],
            "carencia": d["carencia"],
            "valor_proposto": d["valor_proposto"],
            "tipo_envio_docs": d["tipo_envio_docs"],
            "data_envio_docs": d["data_envio_docs"],
            "faixa_honorario_idx": d["faixa_honorario_idx"],
            "percentual_honorario": d["percentual_honorario"],
            "valor_cheio_os": d["valor_cheio_os"],
            "valor_projeto_tecnico": d["valor_cheio_os"],
            "desconto_faixa": d["desconto_faixa"],
            "desconto_extra": d["desconto_extra"],
            "desconto": d["desconto"],
            "acrescimos": d["acrescimos"],
            "valor_total_os": d["valor_total_os"],
            "forma_pagamento": d["forma_pagamento"],
            "num_parcelas": d["num_parcelas"],
            "valor_parcela": d["valor_parcela"],
            "avalista_nome": d["avalista_nome"],
            "avalista_cpf": d["avalista_cpf"],
            "conjuge_avalista_nome": d["conjuge_avalista_nome"],
            "conjuge_avalista_cpf": d["conjuge_avalista_cpf"],
            "credito_tipo": d["credito_tipo"],
            "credito_valor": d["credito_valor"],
            "beneficio_valor": d["beneficio_valor"],
            "parcela_consorcio": d["parcela_consorcio"],
            "num_parcelas_consorcio": d["num_parcelas_consorcio"],
            "parecer_agencia": d["parecer_agencia"],
            "checklist_docs": json.dumps(d["checklist_docs"], ensure_ascii=False),
            "dados_producao": json.dumps(d["dados_producao"], ensure_ascii=False),
            "renda_bruta_anual": d["renda_bruta_anual"],
            "criado_por": usuario_atual,
        }

        pid_edit = st.session_state.get("proposta_id_edicao")
        if pid_edit:
            params_prop["pid"] = int(pid_edit)
            conn.execute(
                text("""
                    UPDATE propostas SET
                        data_proposta = :data_proposta, local_emissao = :local_emissao,
                        parceiro = :parceiro, banco_destino = :banco_destino,
                        cliente_cpf_cnpj = :cliente_cpf_cnpj,
                        propriedade_beneficiada_id = :propriedade_beneficiada_id,
                        imovel_beneficiado_texto = :imovel_beneficiado_texto,
                        tipo_servico = :tipo_servico, descricao_servico = :descricao_servico,
                        item_financiado = :item_financiado, cultura = :cultura,
                        carencia = :carencia, valor_proposto = :valor_proposto,
                        tipo_envio_docs = :tipo_envio_docs, data_envio_docs = :data_envio_docs,
                        faixa_honorario_idx = :faixa_honorario_idx,
                        percentual_honorario = :percentual_honorario,
                        valor_cheio_os = :valor_cheio_os,
                        valor_projeto_tecnico = :valor_projeto_tecnico,
                        desconto_faixa = :desconto_faixa,
                        desconto_extra = :desconto_extra,
                        desconto = :desconto, acrescimos = :acrescimos,
                        valor_total_os = :valor_total_os, forma_pagamento = :forma_pagamento,
                        num_parcelas = :num_parcelas, valor_parcela = :valor_parcela,
                        avalista_nome = :avalista_nome, avalista_cpf = :avalista_cpf,
                        conjuge_avalista_nome = :conjuge_avalista_nome,
                        conjuge_avalista_cpf = :conjuge_avalista_cpf,
                        credito_tipo = :credito_tipo, credito_valor = :credito_valor,
                        beneficio_valor = :beneficio_valor,
                        parcela_consorcio = :parcela_consorcio,
                        num_parcelas_consorcio = :num_parcelas_consorcio,
                        parecer_agencia = :parecer_agencia,
                        checklist_docs = CAST(:checklist_docs AS jsonb),
                        dados_producao = CAST(:dados_producao AS jsonb),
                        renda_bruta_anual = :renda_bruta_anual,
                        atualizado_em = NOW()
                    WHERE id = :pid
                """),
                params_prop,
            )
            return pid_edit
        else:
            novo_id = conn.execute(
                text("""
                    INSERT INTO propostas (
                        data_proposta, local_emissao, parceiro, banco_destino,
                        cliente_cpf_cnpj, propriedade_beneficiada_id, imovel_beneficiado_texto,
                        tipo_servico, descricao_servico, item_financiado, cultura, carencia,
                        valor_proposto, tipo_envio_docs, data_envio_docs,
                        faixa_honorario_idx, percentual_honorario, valor_cheio_os,
                        valor_projeto_tecnico, desconto_faixa, desconto_extra,
                        desconto, acrescimos, valor_total_os, forma_pagamento,
                        num_parcelas, valor_parcela, avalista_nome, avalista_cpf,
                        conjuge_avalista_nome, conjuge_avalista_cpf,
                        credito_tipo, credito_valor, beneficio_valor,
                        parcela_consorcio, num_parcelas_consorcio, parecer_agencia,
                        checklist_docs, dados_producao, renda_bruta_anual, criado_por
                    ) VALUES (
                        :data_proposta, :local_emissao, :parceiro, :banco_destino,
                        :cliente_cpf_cnpj, :propriedade_beneficiada_id, :imovel_beneficiado_texto,
                        :tipo_servico, :descricao_servico, :item_financiado, :cultura, :carencia,
                        :valor_proposto, :tipo_envio_docs, :data_envio_docs,
                        :faixa_honorario_idx, :percentual_honorario, :valor_cheio_os,
                        :valor_projeto_tecnico, :desconto_faixa, :desconto_extra,
                        :desconto, :acrescimos, :valor_total_os, :forma_pagamento,
                        :num_parcelas, :valor_parcela, :avalista_nome, :avalista_cpf,
                        :conjuge_avalista_nome, :conjuge_avalista_cpf,
                        :credito_tipo, :credito_valor, :beneficio_valor,
                        :parcela_consorcio, :num_parcelas_consorcio, :parecer_agencia,
                        CAST(:checklist_docs AS jsonb), CAST(:dados_producao AS jsonb),
                        :renda_bruta_anual, :criado_por
                    ) RETURNING id
                """),
                params_prop,
            ).scalar()
            st.session_state["proposta_id_edicao"] = novo_id
            return novo_id


# ============================================================================
# 7. INICIALIZAÇÃO E BARRA LATERAL
# ============================================================================
inicializar_estado_proposta()
catalogo_servicos, listas_cat, df_contabilidades = carregar_listas_auxiliares()

with st.sidebar:
    st.markdown(f"### 🌱 {EMPRESA['nome_fantasia']}")
    st.caption(f"👤 Atendente: **{usuario_atual}**")
    if st.session_state.get("proposta_id_edicao"):
        st.info(f"✏️ Editando Proposta **#{st.session_state['proposta_id_edicao']}**")
    else:
        st.success("🆕 Nova Proposta")

    st.button("🆕 Limpar / Nova Proposta", on_click=cb_limpar_formulario, use_container_width=True)

    if st.button("💾 Salvar Proposta Agora", type="primary", use_container_width=True):
        pid = salvar_tudo_no_banco()
        if pid:
            st.success(f"✅ Proposta #{pid} salva com sucesso!")

    st.divider()
    if st.button("🚪 Sair do Sistema", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# ============================================================================
# 8. ABAS PRINCIPAIS DO SISTEMA (100% PORTUGUÊS DO BRASIL)
# ============================================================================
aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "📋 1. Nova Proposta & Cliente",
    "🌱 2. Análise Produtiva",
    "🧾 3. Ordem de Serviço & LGPD",
    "🖨️ 4. Imprimir / PDFs (P&B)",
    "🗂️ 5. Histórico & Cadastros",
])

# ----------------------------------------------------------------------------
# ABA 1: NOVA PROPOSTA & CADASTRO DO CLIENTE
# ----------------------------------------------------------------------------
with aba1:
    st.subheader("🔍 Pesquisar Cliente Cadastrado")
    termo_cli = st.text_input(
        "Digite parte do Nome ou CPF/CNPJ para carregar dados e imóveis salvos:",
        placeholder="Ex.: Poliana ou 123.456.789-99",
    )
    if termo_cli.strip():
        with engine.connect() as conn:
            df_encontrados = pd.read_sql(
                text("""
                    SELECT cpf_cnpj, nome, COALESCE(cidade, '') AS cidade
                    FROM clientes
                    WHERE UPPER(nome) LIKE :t OR cpf_cnpj LIKE :t_num
                    ORDER BY nome LIMIT 20
                """),
                conn,
                params={
                    "t": f"%{termo_cli.strip().upper()}%",
                    "t_num": f"%{apenas_digitos(termo_cli) or termo_cli.strip()}%",
                },
            )
        if not df_encontrados.empty:
            opcoes_cli = {
                f"{r['nome']} — {fmt_doc(r['cpf_cnpj'])} ({r['cidade']})": r["cpf_cnpj"]
                for _, r in df_encontrados.iterrows()
            }
            escolhido = st.selectbox("Selecione o cliente encontrado:", list(opcoes_cli.keys()))
            st.button(
                "📥 Carregar Dados e Imóveis deste Cliente",
                on_click=cb_carregar_cliente,
                args=(opcoes_cli[escolhido],),
            )
        else:
            st.caption("Nenhum cliente encontrado com esse termo. Preencha os campos abaixo para cadastrar.")

    st.divider()
    st.subheader("📄 Dados da Proposta e do Produtor")

    c1, c2, c3, c4 = st.columns(4)
    c1.text_input("Local de Emissão", key="local_emissao")
    c2.date_input("Data da Proposta", key="data_proposta", format="DD/MM/YYYY")
    c3.text_input("Parceiro / Escritório", key="parceiro")
    bancos_lista = listas_cat["BANCO"]
    if st.session_state["banco_destino"] not in bancos_lista:
        bancos_lista = [st.session_state["banco_destino"]] + bancos_lista
    c4.selectbox("Banco Destino", bancos_lista, key="banco_destino")

    p1, p2, p3, p4 = st.columns([2.2, 1.4, 1.2, 1.2])
    p1.text_input("Nome Completo do Produtor *", key="cliente_nome")
    p2.text_input(
        "CPF ou CNPJ *",
        key="cliente_cpf",
        placeholder="000.000.000-00 ou 00.000.000/0000-00",
        help="Digite apenas números e aperte Enter/Tab: os pontos, traço e barra entram automaticamente.",
        on_change=cb_formatar_doc,
        args=("cliente_cpf",),
    )
    p3.text_input("Telefone / WhatsApp", key="cliente_telefone", placeholder="(32) 99999-9999")
    tipos_cli = listas_cat["TIPO_CLIENTE"]
    if st.session_state["tipo_cliente"] not in tipos_cli:
        tipos_cli = [st.session_state["tipo_cliente"]] + tipos_cli
    p4.selectbox("Tipo de Cliente", tipos_cli, key="tipo_cliente")

    # Endereço com busca automática de CEP (CORRIGIDA NO ITEM 14!)
    e1, e_btn, e2, e3 = st.columns([1.2, 0.9, 2.5, 1.4])
    e1.text_input("CEP", key="cep", placeholder="00000-000")
    e_btn.write("")
    e_btn.write("")
    e_btn.button("🔎 Buscar CEP", on_click=cb_buscar_cep, use_container_width=True)
    e2.text_input("Rua / Logradouro", key="rua")
    e3.text_input("Localidade / Comunidade", key="localidade")

    # Feedback claro sobre a busca do CEP
    aviso_cep = st.session_state.get("aviso_cep", "")
    if aviso_cep.startswith("ok:"):
        st.success(aviso_cep[3:])
    elif aviso_cep.startswith("info:"):
        st.info(aviso_cep[5:])
    elif aviso_cep.startswith("erro:"):
        st.warning(aviso_cep[5:])

    e4, e5, e6 = st.columns([2, 2, 0.8])
    e4.text_input("Bairro", key="bairro")
    e5.text_input("Cidade", key="cidade")
    e6.text_input("UF", key="uf", max_chars=2)

    # Imóvel Beneficiado
    props_atuais = st.session_state.get("propriedades_lista", [])
    opcoes_imov = [
        f"{p['nome']} Mat {p['matricula']}".strip() if p.get("matricula") else p.get("nome", "")
        for p in props_atuais if p.get("nome")
    ]
    im1, im2 = st.columns([2, 1.5])
    im1.text_input(
        "Imóvel Beneficiado (Nome + Matrícula)",
        key="imovel_beneficiado_texto",
        help="Você pode digitar livremente ou selecionar ao lado um imóvel já cadastrado na Aba 2.",
    )
    if opcoes_imov:
        im2.selectbox(
            "Ou selecionar imóvel salvo do cliente:",
            ["(Manter digitado)"] + opcoes_imov,
            key="seletor_imovel_salvo",
            on_change=cb_aplicar_imovel_salvo,
        )

    # ========================================================================
    # OPERAÇÃO DE CRÉDITO: LINHA -> SERVIÇO -> ITENS FINANCIÁVEIS -> CULTURAS MG
    # ========================================================================
    st.markdown("#### 💰 Operação de Crédito, Linha, Itens Financiáveis e Culturas (MG)")

    linhas_disponiveis = ["TODAS AS LINHAS"] + sorted({v["linha"] for v in catalogo_servicos.values()})
    fl1, fl2 = st.columns([1.2, 2.8])
    linha_filtro = fl1.selectbox("Filtrar por Linha de Crédito", linhas_disponiveis, key="filtro_linha_credito")

    if linha_filtro == "TODAS AS LINHAS":
        servicos_filtrados = list(catalogo_servicos.keys())
    else:
        servicos_filtrados = [k for k, v in catalogo_servicos.items() if v["linha"] == linha_filtro]

    if st.session_state["tipo_servico"] not in servicos_filtrados and servicos_filtrados:
        st.session_state["tipo_servico"] = servicos_filtrados[0]
        cb_ao_trocar_servico(catalogo_servicos)

    fl2.selectbox(
        "Linha + Tipo de Serviço (preenche a descrição da Ordem de Serviço automaticamente)",
        servicos_filtrados,
        key="tipo_servico",
        on_change=cb_ao_trocar_servico,
        args=(catalogo_servicos,),
    )

    op1, op2, op3 = st.columns(3)
    # Itens financiáveis filtrados pela linha/serviço escolhido!
    info_serv_atual = catalogo_servicos.get(st.session_state["tipo_servico"], {})
    itens_da_linha = list(info_serv_atual.get("itens", [])) or listas_cat["TODOS_ITENS"]
    opcoes_item = itens_da_linha + ["OUTRO ITEM (DIGITAR MANUALMENTE)"]
    if st.session_state["item_financiado"] not in opcoes_item:
        if st.session_state["item_financiado"]:
            opcoes_item = [st.session_state["item_financiado"]] + opcoes_item
        else:
            st.session_state["item_financiado"] = opcoes_item[0]

    op1.selectbox(
        "Item Financiável desta Linha",
        opcoes_item,
        key="item_financiado",
        help="Lista filtrada conforme os itens aceitos pela linha de crédito escolhida acima.",
    )
    if st.session_state["item_financiado"] == "OUTRO ITEM (DIGITAR MANUALMENTE)":
        op1.text_input("Digite o item financiado:", key="item_financiado_custom")

    # Culturas principais de Minas Gerais
    lista_cult = listas_cat["CULTURA"]
    if st.session_state["cultura"] not in lista_cult:
        lista_cult = [st.session_state["cultura"]] + lista_cult
    op2.selectbox("Cultura / Atividade Principal (Minas Gerais)", lista_cult, key="cultura")

    # Carência (incluindo SIM (1 ano))
    lista_car = listas_cat["CARENCIA"]
    if st.session_state["carencia"] not in lista_car:
        lista_car = [st.session_state["carencia"]] + lista_car
    op3.selectbox("Carência", lista_car, key="carencia")

    op4, op5 = st.columns(2)
    op4.number_input(
        "Valor Proposto (R$)",
        min_value=0.0,
        step=1000.0,
        format="%.2f",
        key="valor_proposto",
    )

    nomes_cont = [""] + df_contabilidades["nome"].tolist()
    mapa_cnpj = dict(zip(df_contabilidades["nome"], df_contabilidades["cnpj"]))
    if st.session_state["contabilidade_nome"] not in nomes_cont:
        nomes_cont.append(st.session_state["contabilidade_nome"])
    cont_esc = op5.selectbox("Contabilidade do Produtor", nomes_cont, key="contabilidade_nome")
    st.session_state["contabilidade_cnpj"] = fmt_doc(mapa_cnpj.get(cont_esc, ""))

    # Checklist de Documentos
    st.markdown("#### ✅ Checklist de Documentos")
    chk = st.session_state.get("checklist_docs", {})
    ck1, ck2, ck3 = st.columns(3)
    with ck1:
        st.caption("**PROPONENTE**")
        for doc_nome in DOCS_PROPONENTE:
            chave = f"prop_{doc_nome}"
            chk[chave] = st.checkbox(doc_nome, value=bool(chk.get(chave, False)), key=f"ui_{chave}")
    with ck2:
        st.caption("**IMÓVEL**")
        for doc_nome in DOCS_IMOVEL:
            chave = f"imov_{doc_nome}"
            chk[chave] = st.checkbox(doc_nome, value=bool(chk.get(chave, False)), key=f"ui_{chave}")
        lista_envio = listas_cat["TIPO_ENVIO"]
        if st.session_state["tipo_envio_docs"] not in lista_envio:
            lista_envio = [st.session_state["tipo_envio_docs"]] + lista_envio
        st.selectbox("Tipo de Envio dos Documentos", lista_envio, key="tipo_envio_docs")
        st.text_input("Data de Envio dos Docs", key="data_envio_docs", placeholder="DD/MM/AAAA")
    with ck3:
        st.caption("**COOBRIGADOS**")
        for doc_nome in DOCS_COOBRIGADOS:
            chave = f"coob_{doc_nome}"
            chk[chave] = st.checkbox(doc_nome, value=bool(chk.get(chave, False)), key=f"ui_{chave}")
    st.session_state["checklist_docs"] = chk

    # ========================================================================
    # ITEM 9: MARGEM DE CRÉDITO PESSOAL E AVALISTAS TOTALMENTE SEPARADOS!
    # ========================================================================
    st.divider()
    col_margem, col_aval = st.columns(2)

    with col_margem:
        st.markdown("#### 💳 Margem Crédito Pessoal e Consórcio")
        m1, m2 = st.columns(2)
        lista_tc_cred = [""] + listas_cat["TIPO_CREDITO"]
        if st.session_state["credito_tipo"] not in lista_tc_cred:
            lista_tc_cred.append(st.session_state["credito_tipo"])
        m1.selectbox("Tipo de Crédito Pessoal", lista_tc_cred, key="credito_tipo")
        m2.number_input("Valor do Crédito (R$)", min_value=0.0, format="%.2f", key="credito_valor")

        m3, m4 = st.columns(2)
        m3.number_input("Valor do Benefício (R$)", min_value=0.0, format="%.2f", key="beneficio_valor")
        m4.number_input("Parcela Consórcio (R$)", min_value=0.0, format="%.2f", key="parcela_consorcio")
        st.number_input("Nº de Parcelas do Consórcio", min_value=0, step=1, key="num_parcelas_consorcio")

    with col_aval:
        st.markdown("#### 🤝 Avalistas (Avalista e Cônjuge)")
        st.text_input("Nome Completo do Avalista", key="avalista_nome")
        st.text_input(
            "CPF/CNPJ do Avalista",
            key="avalista_cpf",
            placeholder="000.000.000-00",
            on_change=cb_formatar_doc,
            args=("avalista_cpf",),
        )
        st.text_input("Nome Completo do Cônjuge do Avalista", key="conjuge_avalista_nome")
        st.text_input(
            "CPF do Cônjuge do Avalista",
            key="conjuge_avalista_cpf",
            placeholder="000.000.000-00",
            on_change=cb_formatar_doc,
            args=("conjuge_avalista_cpf",),
        )

    # ========================================================================
    # ITEM 10: PARECER DA AGÊNCIA BANCÁRIA
    # ========================================================================
    st.divider()
    st.markdown("#### 🏦 Parecer da Agência Bancária")
    st.text_area(
        "Observações / Parecer da Agência (opcional — se deixar em branco, o PDF imprime o quadro livre para preenchimento à mão na agência):",
        key="parecer_agencia",
        height=75,
    )


# ----------------------------------------------------------------------------
# ABA 2: ANÁLISE PRODUTIVA (PRODUÇÃO)
# ----------------------------------------------------------------------------
with aba2:
    st.subheader("🌱 Análise Produtiva e Propriedades do Produtor")
    st.caption("A primeira propriedade representa o Imóvel Beneficiado. As demais entram como propriedades adicionais / garantias.")

    props = st.session_state["propriedades_lista"]
    col_add, col_rem = st.columns([1, 1])
    if col_add.button("➕ Adicionar Outra Propriedade"):
        props.append(_propriedade_vazia())
        st.rerun()
    if len(props) > 1 and col_rem.button("➖ Remover Última Propriedade"):
        props.pop()
        st.rerun()

    for idx, p in enumerate(props):
        titulo_box = "🏡 Propriedade 1 (Beneficiada)" if idx == 0 else f"🏡 Propriedade {idx + 1}"
        with st.expander(f"{titulo_box} — {p.get('nome') or 'Sem nome'}", expanded=(idx == 0)):
            r1c1, r1c2, r1c3, r1c4 = st.columns([2, 1, 1, 1])
            p["nome"] = r1c1.text_input("Nome da Propriedade", value=p.get("nome", ""), key=f"p_nome_{idx}")
            p["matricula"] = r1c2.text_input("Matrícula", value=p.get("matricula", ""), key=f"p_mat_{idx}")
            p["num_pes"] = r1c3.number_input("Nº Pés de Café", min_value=0, step=100, value=int(p.get("num_pes") or 0), key=f"p_pes_{idx}")
            p["espacamento"] = r1c4.text_input("Espaçamento", value=p.get("espacamento", ""), key=f"p_esp_{idx}")

            r2c1, r2c2, r2c3 = st.columns(3)
            p["variedades"] = r2c1.text_input("Variedades", value=p.get("variedades", ""), key=f"p_var_{idx}")
            p["idade"] = r2c2.text_input("Idade da Lavoura", value=p.get("idade", ""), key=f"p_id_{idx}")
            p["prev_2027"] = r2c3.text_input("Previsão Safra 2027", value=p.get("prev_2027", ""), key=f"p_pr27_{idx}")

            r3c1, r3c2, r3c3 = st.columns(3)
            p["prod_2026"] = r3c1.text_input("Produção 2026", value=p.get("prod_2026", ""), key=f"p_p26_{idx}")
            p["prod_2025"] = r3c2.text_input("Produção 2025", value=p.get("prod_2025", ""), key=f"p_p25_{idx}")
            p["prod_2024"] = r3c3.text_input("Produção 2024", value=p.get("prod_2024", ""), key=f"p_p24_{idx}")

            r4c1, r4c2, r4c3 = st.columns(3)
            p["venda_2026"] = r4c1.number_input("Valor de Venda 2026 (R$)", min_value=0.0, step=500.0, value=float(p.get("venda_2026") or 0), key=f"p_v26_{idx}", format="%.2f")
            p["venda_2025"] = r4c2.number_input("Valor de Venda 2025 (R$)", min_value=0.0, step=500.0, value=float(p.get("venda_2025") or 0), key=f"p_v25_{idx}", format="%.2f")
            p["venda_2024"] = r4c3.number_input("Valor de Venda 2024 (R$)", min_value=0.0, step=500.0, value=float(p.get("venda_2024") or 0), key=f"p_v24_{idx}", format="%.2f")

    st.divider()
    st.markdown("#### 🐄 Semoventes, Renda Extra e Bens")
    sem = st.session_state["semoventes"]
    s1, s2, s3 = st.columns(3)
    sem["vacas_leite"] = s1.number_input("Vacas de Leite (qtd)", min_value=0, step=1, value=int(sem.get("vacas_leite") or 0))
    sem["litros_dia"] = s2.number_input("Litros por Dia", min_value=0.0, step=5.0, value=float(sem.get("litros_dia") or 0))
    sem["preco_litro"] = s3.number_input("Preço por Litro (R$)", min_value=0.0, step=0.10, value=float(sem.get("preco_litro") or 0), format="%.2f")

    s4, s5, s6 = st.columns(3)
    sem["boi_corte"] = s4.number_input("Boi de Corte (qtd)", min_value=0, step=1, value=int(sem.get("boi_corte") or 0))
    sem["novilhas"] = s5.number_input("Novilhas (qtd)", min_value=0, step=1, value=int(sem.get("novilhas") or 0))
    sem["bezerros"] = s6.number_input("Bezerros (qtd)", min_value=0, step=1, value=int(sem.get("bezerros") or 0))

    re1, re2, re3, re4 = st.columns([2, 1, 2, 1])
    re1.text_input("Renda Extra 1 (Descrição)", key="renda_extra_1_desc")
    re2.number_input("Valor Renda 1 (R$)", min_value=0.0, step=500.0, format="%.2f", key="renda_extra_1_val")
    re3.text_input("Renda Extra 2 (Descrição)", key="renda_extra_2_desc")
    re4.number_input("Valor Renda 2 (R$)", min_value=0.0, step=500.0, format="%.2f", key="renda_extra_2_val")

    st.text_area("Relação de Bens (máquinas, veículos, benfeitorias)", key="bens", height=80)

    resumo_prod = montar_dicionario_proposta()
    st.metric("💵 Renda Bruta Anual Calculada", fmt_moeda(resumo_prod["renda_bruta_anual"]))


# ----------------------------------------------------------------------------
# ABA 3: ORDEM DE SERVIÇO (ITEM 7: VALOR CHEIO 2% + DESCONTO DA FAIXA) & LGPD
# ----------------------------------------------------------------------------
with aba3:
    st.subheader("🧾 Ordem de Serviço — Valor Cheio (2,00%) e Desconto Concedido")
    st.caption(
        "Na impressão da Ordem de Serviço, o sistema sempre exibe o Valor Cheio (2,00%) nos honorários e destaca "
        "no campo Desconto a redução concedida pela faixa escolhida abaixo."
    )

    st.text_area(
        "Descrição do Serviço (preenchida automaticamente pela Linha + Serviço escolhidos na Aba 1):",
        key="descricao_servico",
        height=95,
    )

    os1, os2, os3, os4 = st.columns([2.0, 1.0, 1.0, 0.9])
    opcoes_faixa_chaves = list(FAIXAS_HONORARIOS.keys())
    os1.selectbox(
        "Faixa de Honorários (Define o Desconto sobre 2,00%)",
        options=opcoes_faixa_chaves,
        format_func=lambda k: FAIXAS_HONORARIOS[k]["rotulo"],
        key="faixa_honorario_idx",
    )
    os2.number_input("Desconto Extra Manual (R$)", min_value=0.0, step=100.0, format="%.2f", key="desconto_extra")
    os3.number_input("Acréscimos (R$)", min_value=0.0, step=100.0, format="%.2f", key="acrescimos")
    os4.number_input("Nº de Parcelas", min_value=1, step=1, key="num_parcelas")

    st.text_input("Forma de Pagamento", key="forma_pagamento")

    d_calc = montar_dicionario_proposta()
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Valor Proposto", fmt_moeda(d_calc["valor_proposto"]))
    k2.metric("Valor Cheio (2,00%)", fmt_moeda(d_calc["valor_cheio_os"]))
    k3.metric(
        f"Desconto Concedido ({d_calc['percentual_desconto_faixa']*100:.2f}%)",
        f"- {fmt_moeda(d_calc['desconto'])}" if d_calc["desconto"] > 0 else fmt_moeda(0),
    )
    k4.metric("TOTAL DA OS", fmt_moeda(d_calc["valor_total_os"]))
    k5.metric(f"{d_calc['num_parcelas']}x Parcela(s)", fmt_moeda(d_calc["valor_parcela"]))

    st.divider()
    st.subheader("🔒 Conferência do Termo LGPD (Proteção de Dados)")
    st.info(
        f"**Titular:** {d_calc['cliente_nome'] or '(preencher na Aba 1)'} | **CPF/CNPJ:** {fmt_doc(d_calc['cliente_cpf'])}\n\n"
        f"**Contabilidade:** {d_calc['contabilidade_nome'] or 'Não informada'} "
        f"(CNPJ: {fmt_doc(d_calc['contabilidade_cnpj']) or '—'}) | **Banco:** {d_calc['banco_destino']}"
    )

    if st.button("💾 Salvar Proposta e Atualizar Cadastro no Banco", type="primary", use_container_width=True):
        pid = salvar_tudo_no_banco()
        if pid:
            st.success(f"✅ Proposta #{pid} salva com sucesso no PostgreSQL! Agora você pode gerar os PDFs na Aba 4.")


# ----------------------------------------------------------------------------
# ABA 4: IMPRESSÃO / PDFs (100% PRETO E BRANCO, 1 PÁGINA/FOLHA, MARCA D'ÁGUA)
# ----------------------------------------------------------------------------
with aba4:
    st.subheader("🖨️ Impressão de Pacotes Bancários e Documentos Avulsos")
    st.info(
        "🖨️ **Padrão de Impressão Ativado:** Preto e Branco • Margens estreitas (folha A4 cheia, 1 página por documento) • "
        "Marca d'água oficial da Regularize em todas as folhas."
    )

    d_pdf = montar_dicionario_proposta()
    nome_arquivo_base = re.sub(r"[^A-Za-z0-9_-]+", "_", d_pdf["cliente_nome"] or "PROPOSTA").strip("_")

    col_pac, col_ind = st.columns(2)

    with col_pac:
        st.markdown("### 📦 Pacote Completo por Instituição")
        banco_pacote = st.selectbox("Escolha o Pacote Bancário:", list(PACOTES_BANCOS.keys()))
        incluir_abas_cliente = st.multiselect(
            "Quais documentos do cliente incluir no início do pacote?",
            options=DOCUMENTOS_CLIENTE_PADRAO + ["GALPÃO DE GRÃOS"],
            default=DOCUMENTOS_CLIENTE_PADRAO,
        )
        incluir_aval = st.checkbox(
            "Incluir folhas de Avalista e Cônjuge (quando preenchidos no Banco do Brasil)",
            value=True,
        )

        docs_do_pacote = list(incluir_abas_cliente) + list(PACOTES_BANCOS[banco_pacote])
        if banco_pacote == "BANCO DO BRASIL" and incluir_aval:
            if d_pdf["avalista_nome"]:
                docs_do_pacote.extend(["BB AVAL", "SICOR AVAL"])
            if d_pdf["conjuge_avalista_nome"]:
                docs_do_pacote.extend(["BB CONJUGE AVAL", "SICOR CONJUGE AVAL"])

        st.caption(f"Total de folhas A4 neste PDF: **{len(docs_do_pacote)}** (" + ", ".join(docs_do_pacote) + ")")
        if docs_do_pacote:
            pdf_pacote = gerar_pdf_bytes(d_pdf, docs_do_pacote)
            st.download_button(
                label=f"📥 Baixar Pacote PDF (P&B) — {banco_pacote}",
                data=pdf_pacote,
                file_name=f"PACOTE_{banco_pacote.replace(' ', '_')}_{nome_arquivo_base}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )

    with col_ind:
        st.markdown("### 📄 Documento Individual (1 Folha A4)")
        doc_avulso = st.selectbox("Escolha qualquer um dos 23 documentos:", TODOS_OS_DOCUMENTOS)
        pdf_avulso = gerar_pdf_bytes(d_pdf, [doc_avulso])
        st.download_button(
            label=f"📥 Baixar PDF Individual (P&B) — {doc_avulso}",
            data=pdf_avulso,
            file_name=f"{doc_avulso.replace(' ', '_')}_{nome_arquivo_base}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ----------------------------------------------------------------------------
# ABA 5: HISTÓRICO EM PT-BR & CADASTRO DE CONTABILIDADES
# ----------------------------------------------------------------------------
with aba5:
    st.subheader("🗂️ Histórico de Propostas Salvas")
    f1, f2, f3 = st.columns([2, 1.5, 1])
    busca_hist = f1.text_input("Filtrar por Nome ou CPF/CNPJ:", placeholder="Digite nome ou números do CPF/CNPJ")
    banco_hist = f2.selectbox("Filtrar por Banco:", ["TODOS"] + listas_cat["BANCO"])
    limite_hist = f3.number_input("Máximo de registros", min_value=20, max_value=2000, value=200, step=50)

    sql_hist = text("""
        SELECT p.id, p.data_proposta, c.nome AS cliente, p.cliente_cpf_cnpj AS cpf_cnpj,
               p.banco_destino AS banco, p.tipo_servico AS servico,
               p.item_financiado AS item, p.valor_proposto, p.valor_total_os,
               p.criado_por, p.criado_em
        FROM propostas p
        JOIN clientes c ON c.cpf_cnpj = p.cliente_cpf_cnpj
        WHERE (:busca = '' OR UPPER(c.nome) LIKE :termo OR p.cliente_cpf_cnpj LIKE :termo_num)
          AND (:banco = 'TODOS' OR p.banco_destino = :banco)
        ORDER BY p.id DESC
        LIMIT :lim
    """)
    with engine.connect() as conn:
        df_hist = pd.read_sql(
            sql_hist,
            conn,
            params={
                "busca": busca_hist.strip(),
                "termo": f"%{busca_hist.strip().upper()}%",
                "termo_num": f"%{apenas_digitos(busca_hist) or busca_hist.strip()}%",
                "banco": banco_hist,
                "lim": int(limite_hist),
            },
        )

    if not df_hist.empty:
        df_exibir = df_hist.copy()
        df_exibir["cpf_cnpj"] = df_exibir["cpf_cnpj"].apply(fmt_doc)
        df_exibir["data_proposta"] = pd.to_datetime(df_exibir["data_proposta"]).dt.strftime("%d/%m/%Y")
        df_exibir["valor_proposto_fmt"] = df_exibir["valor_proposto"].apply(fmt_moeda)
        df_exibir["valor_total_os_fmt"] = df_exibir["valor_total_os"].apply(fmt_moeda)
        df_exibir["criado_em"] = pd.to_datetime(df_exibir["criado_em"]).dt.strftime("%d/%m/%Y %H:%M")

        df_tabela = df_exibir[[
            "id", "data_proposta", "cliente", "cpf_cnpj", "banco",
            "servico", "item", "valor_proposto_fmt", "valor_total_os_fmt",
            "criado_por", "criado_em",
        ]].rename(columns={
            "id": "Nº",
            "data_proposta": "Data",
            "cliente": "Produtor / Cliente",
            "cpf_cnpj": "CPF/CNPJ",
            "banco": "Banco",
            "servico": "Linha / Serviço",
            "item": "Item Financiado",
            "valor_proposto_fmt": "Valor Proposto",
            "valor_total_os_fmt": "Total OS",
            "criado_por": "Atendente",
            "criado_em": "Salvo em",
        })
        st.dataframe(df_tabela, use_container_width=True, hide_index=True)

        c_load, c_exp = st.columns([2, 1])
        op_props = {
            f"#{r['id']} | {pd.to_datetime(r['data_proposta']).strftime('%d/%m/%Y')} | {r['cliente']} ({r['banco']} — {fmt_moeda(r['valor_proposto'])})": int(r["id"])
            for _, r in df_hist.iterrows()
        }
        prop_sel = c_load.selectbox("Abrir proposta do histórico para editar ou reimprimir:", list(op_props.keys()))
        c_load.button(
            "📂 Carregar Proposta Selecionada",
            on_click=cb_carregar_proposta,
            args=(op_props[prop_sel],),
        )

        buf_xlsx = io.BytesIO()
        with pd.ExcelWriter(buf_xlsx, engine="openpyxl") as writer:
            df_tabela.to_excel(writer, index=False, sheet_name="Historico_Propostas")
        c_exp.write("")
        c_exp.write("")
        c_exp.download_button(
            "📥 Exportar Histórico em Excel (.xlsx)",
            data=buf_xlsx.getvalue(),
            file_name="historico_propostas_regularize.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        st.info("Nenhuma proposta salva encontrada para os filtros informados.")

    st.divider()
    st.subheader("🏢 Cadastrar Nova Contabilidade")
    with st.form("form_nova_contabilidade", clear_on_submit=True):
        nc1, nc2 = st.columns(2)
        novo_nome_cont = nc1.text_input("Nome do Escritório / Contador")
        novo_cnpj_cont = nc2.text_input("CNPJ (opcional)", placeholder="00.000.000/0000-00")
        if st.form_submit_button("➕ Salvar Contabilidade"):
            if novo_nome_cont.strip():
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO contabilidades (nome, cnpj)
                            VALUES (:n, :c)
                            ON CONFLICT (nome) DO UPDATE SET cnpj = EXCLUDED.cnpj
                        """),
                        {"n": novo_nome_cont.strip(), "c": fmt_doc(novo_cnpj_cont.strip())},
                    )
                carregar_listas_auxiliares.clear()
                st.success(f"✅ Contabilidade '{novo_nome_cont.strip()}' cadastrada com sucesso!")
                st.rerun()
            else:
                st.warning("Informe o nome da contabilidade.")
