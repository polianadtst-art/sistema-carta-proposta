# ============================================================================
# ARQUIVO: app.py
# O QUE ESTE ARQUIVO FAZ:
#   É o coração do seu sistema web multiusuário (funciona no computador e no
#   celular). Várias pessoas podem abrir o link ao mesmo tempo, consultar
#   clientes, salvar propostas e baixar PDFs sem travar e sem ver a base bruta.
#
#   Você NÃO precisa mexer neste arquivo para configurar o sistema!
#   - Para mudar dados da empresa/taxas: edite apenas o arquivo config.py
#   - Para mudar senha do banco ou usuários: edite apenas o Secrets no Streamlit
# ============================================================================

import io
import json
import re
import urllib.request
from datetime import date, datetime

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from config import (
    DOCS_COOBRIGADOS,
    DOCS_IMOVEL,
    DOCS_PROPONENTE,
    DOCUMENTOS_CLIENTE_PADRAO,
    EMPRESA,
    FAIXAS_HONORARIOS,
    PACOTES_BANCOS,
    TODOS_OS_DOCUMENTOS,
)
from pdf_generator import fmt_doc, fmt_moeda, gerar_pdf_bytes

# ============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ============================================================================
st.set_page_config(
    page_title=f"Sistema Carta-Proposta | {EMPRESA['nome_fantasia']}",
    page_icon="🌱",
    layout="wide",
)


# ============================================================================
# 2. CONEXÃO SEGURA COM O BANCO POSTGRESQL (SUPABASE)
# ============================================================================
@st.cache_resource
def conectar_banco():
    """
    Cria a conexão segura com o PostgreSQL lendo a senha oculta nos 'Secrets'.
    pool_pre_ping=True garante que a conexão nunca caia mesmo se ficar ociosa.
    """
    if "DATABASE_URL" not in st.secrets:
        st.error(
            "❌ Configuração pendente: 'DATABASE_URL' não foi encontrada nos Secrets.\n"
            "Siga a Fase 4 do guia passo a passo para colar o link do Supabase."
        )
        st.stop()
    return create_engine(
        st.secrets["DATABASE_URL"],
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


engine = conectar_banco()


# ============================================================================
# 3. TELA DE LOGIN (CONTROLE DE ACESSO MULTIUSUÁRIO)
# ============================================================================
def verificar_login():
    """Exibe tela de login e protege o sistema contra acesso não autorizado."""
    if st.session_state.get("usuario_logado"):
        return st.session_state["usuario_logado"]

    st.markdown(f"## 🌱 {EMPRESA['nome_fantasia']}")
    st.caption("Sistema Web de Carta-Proposta, Análise Produtiva e Ordem de Serviço")

    col_e, col_m, col_d = st.columns([1, 1.5, 1])
    with col_m:
        with st.form("form_login"):
            st.subheader("Acesso Restrito à Equipe")
            email = st.text_input("Usuário ou E-mail").strip().lower()
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar no Sistema", use_container_width=True)

            if entrar:
                usuarios_permitidos = dict(st.secrets.get("usuarios", {}))
                # Compara ignorando maiúsculas/minúsculas no e-mail
                mapa_lower = {k.strip().lower(): str(v) for k, v in usuarios_permitidos.items()}
                if email in mapa_lower and senha == mapa_lower[email]:
                    st.session_state["usuario_logado"] = email
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos. Verifique com a administração.")
    st.stop()


usuario_atual = verificar_login()


# ============================================================================
# 4. FUNÇÕES AUXILIARES DE LEITURA DO BANCO E FORMATAÇÃO
# ============================================================================
def apenas_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


@st.cache_data(ttl=60)
def carregar_listas_auxiliares():
    """Carrega serviços, itens, culturas, bancos e contabilidades do PostgreSQL."""
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
    listas_por_cat = {}
    for cat, grupo in df_listas.groupby("categoria"):
        listas_por_cat[cat] = grupo["valor"].tolist()
    servicos_dict = dict(zip(df_serv["tipo_servico"], df_serv["descricao_servico"]))
    return servicos_dict, listas_por_cat, df_cont


def buscar_cep_online(cep_texto):
    """Consulta o CEP gratuitamente no ViaCEP para preencher Rua, Bairro, Cidade e UF."""
    dig = apenas_digitos(cep_texto)
    if len(dig) != 8:
        return None
    try:
        url = f"https://viacep.com.br/ws/{dig}/json/"
        with urllib.request.urlopen(url, timeout=4) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
            if "erro" in dados:
                return None
            return dados
    except Exception:
        return None


def inicializar_estado_proposta():
    """Prepara a memória isolada da sessão de cada usuário (um nunca interfere no outro)."""
    padrao = {
        "proposta_id_edicao": None,
        "cliente_atualizado_em_lido": None,
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
        "contabilidade_nome": "",
        "contabilidade_cnpj": "",
        "imovel_beneficiado_texto": "",
        "tipo_servico": "",
        "descricao_servico": "",
        "item_financiado": "",
        "cultura": "CAFÉ",
        "carencia": "Não",
        "valor_proposto": 0.0,
        "tipo_envio_docs": "DIGITAL/E-MAIL",
        "data_envio_docs": "",
        "faixa_honorario_idx": 2,
        "desconto": 0.0,
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
        "checklist_docs": {},
        "propriedades_lista": [
            {
                "nome": "", "matricula": "", "num_pes": 0, "espacamento": "",
                "variedades": "", "idade": "", "prev_2027": "",
                "prod_2026": "", "prod_2025": "", "prod_2024": "",
                "venda_2026": 0.0, "venda_2025": 0.0, "venda_2024": 0.0,
            }
        ],
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


def limpar_formulario():
    """Limpa todos os campos para iniciar uma nova proposta do zero."""
    chaves_manter = {"usuario_logado"}
    for k in list(st.session_state.keys()):
        if k not in chaves_manter:
            del st.session_state[k]
    inicializar_estado_proposta()


def carregar_cliente_no_formulario(cpf_cnpj):
    """Busca cliente + propriedades + contabilidade no PostgreSQL e preenche a tela."""
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
            return False

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

    st.session_state["cliente_cpf"] = cli["cpf_cnpj"]
    st.session_state["cliente_nome"] = cli["nome"] or ""
    st.session_state["cliente_telefone"] = cli["telefone"] or ""
    st.session_state["tipo_cliente"] = cli["tipo_cliente"] or "PROPRIETÁRIO"
    st.session_state["cep"] = cli["cep"] or ""
    st.session_state["rua"] = cli["rua"] or ""
    st.session_state["localidade"] = cli["localidade"] or ""
    st.session_state["bairro"] = cli["bairro"] or ""
    st.session_state["cidade"] = cli["cidade"] or EMPRESA["cidade_padrao"]
    st.session_state["uf"] = cli["uf"] or EMPRESA["uf_padrao"]
    st.session_state["contabilidade_nome"] = cli["cont_nome"] or ""
    st.session_state["contabilidade_cnpj"] = cli["cont_cnpj"] or ""
    st.session_state["cliente_atualizado_em_lido"] = str(cli["atualizado_em"])

    if props:
        lista_p = []
        for p in props:
            lista_p.append({
                "nome": p["nome_propriedade"],
                "matricula": p["matricula"],
                "num_pes": int(p["num_pes"] or 0),
                "espacamento": p["espacamento"],
                "variedades": p["variedades"],
                "idade": p["idade"],
                "prev_2027": "", "prod_2026": "", "prod_2025": "", "prod_2024": "",
                "venda_2026": 0.0, "venda_2025": 0.0, "venda_2024": 0.0,
            })
        st.session_state["propriedades_lista"] = lista_p
        p0 = lista_p[0]
        st.session_state["imovel_beneficiado_texto"] = (
            f"{p0['nome']} Mat {p0['matricula']}".strip() if p0["matricula"] else p0["nome"]
        )
    else:
        st.session_state["propriedades_lista"] = [
            {
                "nome": "", "matricula": "", "num_pes": 0, "espacamento": "",
                "variedades": "", "idade": "", "prev_2027": "",
                "prod_2026": "", "prod_2025": "", "prod_2024": "",
                "venda_2026": 0.0, "venda_2025": 0.0, "venda_2024": 0.0,
            }
        ]
    return True


def carregar_proposta_salva(proposta_id):
    """Carrega uma proposta inteira do histórico para edição ou reimpressão."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM propostas WHERE id = :pid"),
            {"pid": int(proposta_id)},
        ).mappings().first()

    if not row:
        return False

    carregar_cliente_no_formulario(row["cliente_cpf_cnpj"])
    st.session_state["proposta_id_edicao"] = row["id"]
    st.session_state["data_proposta"] = row["data_proposta"] or date.today()
    st.session_state["local_emissao"] = row["local_emissao"] or EMPRESA["cidade_padrao"]
    st.session_state["parceiro"] = row["parceiro"] or EMPRESA["nome_fantasia"]
    st.session_state["banco_destino"] = row["banco_destino"] or "BANCO DO BRASIL"
    st.session_state["imovel_beneficiado_texto"] = row["imovel_beneficiado_texto"] or ""
    st.session_state["tipo_servico"] = row["tipo_servico"] or ""
    st.session_state["descricao_servico"] = row["descricao_servico"] or ""
    st.session_state["item_financiado"] = row["item_financiado"] or ""
    st.session_state["cultura"] = row["cultura"] or "CAFÉ"
    st.session_state["carencia"] = row["carencia"] or "Não"
    st.session_state["valor_proposto"] = float(row["valor_proposto"] or 0)
    st.session_state["tipo_envio_docs"] = row["tipo_envio_docs"] or "DIGITAL/E-MAIL"
    st.session_state["data_envio_docs"] = row["data_envio_docs"] or ""
    st.session_state["faixa_honorario_idx"] = int(row["faixa_honorario_idx"] or 2)
    st.session_state["desconto"] = float(row["desconto"] or 0)
    st.session_state["acrescimos"] = float(row["acrescimos"] or 0)
    st.session_state["forma_pagamento"] = row["forma_pagamento"] or "Na emissão da minuta"
    st.session_state["num_parcelas"] = max(1, int(row["num_parcelas"] or 1))
    st.session_state["avalista_nome"] = row["avalista_nome"] or ""
    st.session_state["avalista_cpf"] = row["avalista_cpf"] or ""
    st.session_state["conjuge_avalista_nome"] = row["conjuge_avalista_nome"] or ""
    st.session_state["conjuge_avalista_cpf"] = row["conjuge_avalista_cpf"] or ""
    st.session_state["credito_tipo"] = row["credito_tipo"] or ""
    st.session_state["credito_valor"] = float(row["credito_valor"] or 0)
    st.session_state["beneficio_valor"] = float(row["beneficio_valor"] or 0)
    st.session_state["parcela_consorcio"] = float(row["parcela_consorcio"] or 0)
    st.session_state["num_parcelas_consorcio"] = int(row["num_parcelas_consorcio"] or 0)
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
    return True


def montar_dicionario_proposta():
    """Reúne todos os campos atuais da tela num pacote único para salvar ou gerar PDF."""
    idx_faixa = int(st.session_state.get("faixa_honorario_idx", 2))
    pct = FAIXAS_HONORARIOS.get(idx_faixa, FAIXAS_HONORARIOS[2])["percentual"]
    val_prop = float(st.session_state.get("valor_proposto") or 0)
    val_proj = round(val_prop * pct, 2)
    desc = float(st.session_state.get("desconto") or 0)
    acresc = float(st.session_state.get("acrescimos") or 0)
    total_os = max(0.0, round(val_proj - desc + acresc, 2))
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

    return {
        "local_emissao": st.session_state["local_emissao"],
        "data_proposta": st.session_state["data_proposta"],
        "parceiro": st.session_state["parceiro"],
        "banco_destino": st.session_state["banco_destino"],
        "cliente_cpf": apenas_digitos(st.session_state["cliente_cpf"]),
        "cliente_nome": st.session_state["cliente_nome"].strip().upper(),
        "cliente_telefone": st.session_state["cliente_telefone"],
        "tipo_cliente": st.session_state["tipo_cliente"],
        "cep": st.session_state["cep"],
        "rua": st.session_state["rua"],
        "localidade": st.session_state["localidade"],
        "bairro": st.session_state["bairro"],
        "cidade": st.session_state["cidade"],
        "uf": st.session_state["uf"],
        "contabilidade_nome": st.session_state["contabilidade_nome"],
        "contabilidade_cnpj": st.session_state["contabilidade_cnpj"],
        "imovel_beneficiado_texto": st.session_state["imovel_beneficiado_texto"],
        "tipo_servico": st.session_state["tipo_servico"],
        "descricao_servico": st.session_state["descricao_servico"],
        "item_financiado": st.session_state["item_financiado"],
        "cultura": st.session_state["cultura"],
        "carencia": st.session_state["carencia"],
        "valor_proposto": val_prop,
        "tipo_envio_docs": st.session_state["tipo_envio_docs"],
        "data_envio_docs": st.session_state["data_envio_docs"],
        "faixa_honorario_idx": idx_faixa,
        "percentual_honorario": pct,
        "valor_projeto_tecnico": val_proj,
        "desconto": desc,
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
    """
    Salva Cliente + Propriedades + Proposta em uma transação atômica do PostgreSQL.
    Múltiplos usuários podem clicar neste botão no mesmo segundo sem conflito!
    """
    d = montar_dicionario_proposta()
    if len(d["cliente_cpf"]) not in (11, 14):
        st.error("❌ Informe um CPF (11 dígitos) ou CNPJ (14 dígitos) válido antes de salvar.")
        return None
    if not d["cliente_nome"]:
        st.error("❌ Preencha o Nome do Cliente antes de salvar.")
        return None

    with engine.begin() as conn:
        # 1. Localiza ID da contabilidade selecionada (se houver)
        cont_id = None
        if d["contabilidade_nome"]:
            res_c = conn.execute(
                text("SELECT id FROM contabilidades WHERE nome = :n"),
                {"n": d["contabilidade_nome"]},
            ).first()
            if res_c:
                cont_id = res_c[0]

        # 2. Insere ou atualiza Cliente
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

        # 3. Insere ou atualiza Propriedades do Cliente
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

        # 4. Insere nova proposta ou atualiza proposta em edição
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
            "valor_projeto_tecnico": d["valor_projeto_tecnico"],
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
                        valor_projeto_tecnico = :valor_projeto_tecnico,
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
                        faixa_honorario_idx, percentual_honorario, valor_projeto_tecnico,
                        desconto, acrescimos, valor_total_os, forma_pagamento,
                        num_parcelas, valor_parcela, avalista_nome, avalista_cpf,
                        conjuge_avalista_nome, conjuge_avalista_cpf,
                        credito_tipo, credito_valor, beneficio_valor,
                        parcela_consorcio, num_parcelas_consorcio,
                        checklist_docs, dados_producao, renda_bruta_anual, criado_por
                    ) VALUES (
                        :data_proposta, :local_emissao, :parceiro, :banco_destino,
                        :cliente_cpf_cnpj, :propriedade_beneficiada_id, :imovel_beneficiado_texto,
                        :tipo_servico, :descricao_servico, :item_financiado, :cultura, :carencia,
                        :valor_proposto, :tipo_envio_docs, :data_envio_docs,
                        :faixa_honorario_idx, :percentual_honorario, :valor_projeto_tecnico,
                        :desconto, :acrescimos, :valor_total_os, :forma_pagamento,
                        :num_parcelas, :valor_parcela, :avalista_nome, :avalista_cpf,
                        :conjuge_avalista_nome, :conjuge_avalista_cpf,
                        :credito_tipo, :credito_valor, :beneficio_valor,
                        :parcela_consorcio, :num_parcelas_consorcio,
                        CAST(:checklist_docs AS jsonb), CAST(:dados_producao AS jsonb),
                        :renda_bruta_anual, :criado_por
                    ) RETURNING id
                """),
                params_prop,
            ).scalar()
            st.session_state["proposta_id_edicao"] = novo_id
            return novo_id


# ============================================================================
# 5. INICIALIZAÇÃO E BARRA LATERAL
# ============================================================================
inicializar_estado_proposta()
servicos_dict, listas_cat, df_contabilidades = carregar_listas_auxiliares()

with st.sidebar:
    st.markdown(f"### 🌱 {EMPRESA['nome_fantasia']}")
    st.caption(f"👤 Logado como: **{usuario_atual}**")
    if st.session_state.get("proposta_id_edicao"):
        st.info(f"✏️ Editando Proposta **#{st.session_state['proposta_id_edicao']}**")
    else:
        st.success("🆕 Nova Proposta (ainda não salva)")

    if st.button("🆕 Limpar / Nova Proposta", use_container_width=True):
        limpar_formulario()
        st.rerun()

    if st.button("💾 Salvar Proposta Agora", type="primary", use_container_width=True):
        pid = salvar_tudo_no_banco()
        if pid:
            st.success(f"✅ Proposta #{pid} salva com sucesso!")

    st.divider()
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# ============================================================================
# 6. ABAS PRINCIPAIS DO SISTEMA
# ============================================================================
aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "📋 1. Nova Proposta & Cliente",
    "🌱 2. Análise Produtiva",
    "🧾 3. Ordem de Serviço & LGPD",
    "🖨️ 4. Gerar PDFs & Bancos",
    "🗂️ 5. Histórico & Cadastros",
])

# ----------------------------------------------------------------------------
# ABA 1: NOVA PROPOSTA & CADASTRO DO CLIENTE
# ----------------------------------------------------------------------------
with aba1:
    st.subheader("🔍 Pesquisar Cliente Existente")
    col_b1, col_b2 = st.columns([3, 1])
    termo_cli = col_b1.text_input(
        "Digite parte do Nome ou CPF/CNPJ para carregar dados e imóveis salvos:",
        placeholder="Ex: Poliana ou 12345678999",
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
            if st.button("📥 Carregar Dados e Imóveis deste Cliente"):
                carregar_cliente_no_formulario(opcoes_cli[escolhido])
                st.success("Cliente e propriedades carregados!")
                st.rerun()
        else:
            st.caption("Nenhum cliente encontrado com esse termo. Preencha os campos abaixo para cadastrar.")

    st.divider()
    st.subheader("📄 Dados da Proposta e do Produtor")

    c1, c2, c3, c4 = st.columns(4)
    st.session_state["local_emissao"] = c1.text_input("Local de Emissão", value=st.session_state["local_emissao"])
    st.session_state["data_proposta"] = c2.date_input("Data da Proposta", value=st.session_state["data_proposta"])
    st.session_state["parceiro"] = c3.text_input("Parceiro / Escritório", value=st.session_state["parceiro"])
    bancos_lista = listas_cat.get("BANCO", ["BANCO DO BRASIL", "SICOOB", "BRADESCO", "CRESOL", "CAIXA"])
    idx_banco = bancos_lista.index(st.session_state["banco_destino"]) if st.session_state["banco_destino"] in bancos_lista else 0
    st.session_state["banco_destino"] = c4.selectbox("Banco Destino", bancos_lista, index=idx_banco)

    p1, p2, p3, p4 = st.columns([2.2, 1.3, 1.2, 1.3])
    st.session_state["cliente_nome"] = p1.text_input("Nome Completo do Produtor *", value=st.session_state["cliente_nome"])
    st.session_state["cliente_cpf"] = p2.text_input("CPF ou CNPJ *", value=st.session_state["cliente_cpf"], placeholder="Somente números ou formatado")
    st.session_state["cliente_telefone"] = p3.text_input("Telefone / WhatsApp", value=st.session_state["cliente_telefone"])
    tipos_cli = listas_cat.get("TIPO_CLIENTE", ["PROPRIETÁRIO", "ARRENDATÁRIO", "COMODATÁRIO", "PARCEIRO", "POSSEIRO"])
    idx_tc = tipos_cli.index(st.session_state["tipo_cliente"]) if st.session_state["tipo_cliente"] in tipos_cli else 0
    st.session_state["tipo_cliente"] = p4.selectbox("Tipo de Cliente", tipos_cli, index=idx_tc)

    # Endereço com busca automática de CEP
    e1, e_btn, e2, e3 = st.columns([1.2, 0.8, 2.5, 1.5])
    st.session_state["cep"] = e1.text_input("CEP", value=st.session_state["cep"])
    e_btn.write("")
    if e_btn.button("🔎 Buscar CEP"):
        res_cep = buscar_cep_online(st.session_state["cep"])
        if res_cep:
            st.session_state["rua"] = res_cep.get("logradouro", "")
            st.session_state["bairro"] = res_cep.get("bairro", "")
            st.session_state["cidade"] = res_cep.get("localidade", "")
            st.session_state["uf"] = res_cep.get("uf", "MG")
            st.rerun()
        else:
            st.warning("CEP não encontrado.")
    st.session_state["rua"] = e2.text_input("Rua / Logradouro", value=st.session_state["rua"])
    st.session_state["localidade"] = e3.text_input("Localidade / Comunidade", value=st.session_state["localidade"])

    e4, e5, e6 = st.columns([2, 2, 0.8])
    st.session_state["bairro"] = e4.text_input("Bairro", value=st.session_state["bairro"])
    st.session_state["cidade"] = e5.text_input("Cidade", value=st.session_state["cidade"])
    st.session_state["uf"] = e6.text_input("UF", value=st.session_state["uf"], max_chars=2)

    # Imóvel Beneficiado (sugere os imóveis já cadastrados na Aba 2)
    props_atuais = st.session_state.get("propriedades_lista", [])
    opcoes_imov = [
        f"{p['nome']} Mat {p['matricula']}".strip() if p.get("matricula") else p.get("nome", "")
        for p in props_atuais if p.get("nome")
    ]
    im1, im2 = st.columns([2, 1.5])
    st.session_state["imovel_beneficiado_texto"] = im1.text_input(
        "Imóvel Beneficiado (Nome + Matrícula)",
        value=st.session_state["imovel_beneficiado_texto"],
        help="Dica: você pode escolher um imóvel salvo ao lado ou digitar livremente.",
    )
    if opcoes_imov:
        escolha_imov = im2.selectbox("Ou selecionar imóvel salvo do cliente:", ["(Manter digitado)"] + opcoes_imov)
        if escolha_imov != "(Manter digitado)" and escolha_imov != st.session_state["imovel_beneficiado_texto"]:
            st.session_state["imovel_beneficiado_texto"] = escolha_imov
            st.rerun()

    st.markdown("#### 💰 Operação de Crédito e Contabilidade")
    op1, op2, op3 = st.columns(3)
    lista_servicos = [""] + list(servicos_dict.keys())
    idx_s = lista_servicos.index(st.session_state["tipo_servico"]) if st.session_state["tipo_servico"] in lista_servicos else 0
    novo_serv = op1.selectbox("Tipo de Serviço", lista_servicos, index=idx_s)
    if novo_serv != st.session_state["tipo_servico"]:
        st.session_state["tipo_servico"] = novo_serv
        # Preenche automaticamente a descrição padrão na Ordem de Serviço (igual macro da célula D20!)
        st.session_state["descricao_servico"] = servicos_dict.get(novo_serv, "")

    lista_itens = [""] + listas_cat.get("ITEM", [])
    idx_it = lista_itens.index(st.session_state["item_financiado"]) if st.session_state["item_financiado"] in lista_itens else 0
    st.session_state["item_financiado"] = op2.selectbox("Item Financiado", lista_itens, index=idx_it)

    lista_cult = listas_cat.get("CULTURA", ["CAFÉ", "PECUÁRIA LEITEIRA", "PECUÁRIA DE CORTE", "HORTIFRUTIGRANJEIRO"])
    idx_cu = lista_cult.index(st.session_state["cultura"]) if st.session_state["cultura"] in lista_cult else 0
    st.session_state["cultura"] = op3.selectbox("Cultura Principal", lista_cult, index=idx_cu)

    op4, op5, op6 = st.columns(3)
    lista_car = listas_cat.get("CARENCIA", ["Não", "SIM (2 anos)", "SIM (3 anos)"])
    idx_ca = lista_car.index(st.session_state["carencia"]) if st.session_state["carencia"] in lista_car else 0
    st.session_state["carencia"] = op4.selectbox("Carência", lista_car, index=idx_ca)
    st.session_state["valor_proposto"] = op5.number_input(
        "Valor Proposto (R$)", min_value=0.0, step=1000.0,
        value=float(st.session_state["valor_proposto"]), format="%.2f",
    )

    nomes_cont = [""] + df_contabilidades["nome"].tolist()
    mapa_cnpj = dict(zip(df_contabilidades["nome"], df_contabilidades["cnpj"]))
    idx_ct = nomes_cont.index(st.session_state["contabilidade_nome"]) if st.session_state["contabilidade_nome"] in nomes_cont else 0
    cont_escolhida = op6.selectbox("Contabilidade do Produtor", nomes_cont, index=idx_ct)
    st.session_state["contabilidade_nome"] = cont_escolhida
    st.session_state["contabilidade_cnpj"] = mapa_cnpj.get(cont_escolhida, "")

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
        lista_envio = listas_cat.get("TIPO_ENVIO", ["FÍSICO", "DIGITAL/E-MAIL"])
        idx_env = lista_envio.index(st.session_state["tipo_envio_docs"]) if st.session_state["tipo_envio_docs"] in lista_envio else 0
        st.session_state["tipo_envio_docs"] = st.selectbox("Tipo de Envio", lista_envio, index=idx_env)
        st.session_state["data_envio_docs"] = st.text_input("Data Envio de Docs", value=st.session_state["data_envio_docs"], placeholder="DD/MM/AAAA")
    with ck3:
        st.caption("**COOBRIGADOS**")
        for doc_nome in DOCS_COOBRIGADOS:
            chave = f"coob_{doc_nome}"
            chk[chave] = st.checkbox(doc_nome, value=bool(chk.get(chave, False)), key=f"ui_{chave}")
    st.session_state["checklist_docs"] = chk

    # Margem Crédito Pessoal e Avalistas
    with st.expander("💳 Margem Crédito Pessoal, Consórcio e Avalistas (Clique para abrir)"):
        m1, m2, m3, m4 = st.columns(4)
        lista_tc_cred = [""] + listas_cat.get("TIPO_CREDITO", ["AUTOMÁTICO", "BENEFÍCIO", "CONSIGNADO", "SALÁRIO"])
        idx_cr = lista_tc_cred.index(st.session_state["credito_tipo"]) if st.session_state["credito_tipo"] in lista_tc_cred else 0
        st.session_state["credito_tipo"] = m1.selectbox("Tipo Crédito Pessoal", lista_tc_cred, index=idx_cr)
        st.session_state["credito_valor"] = m2.number_input("Valor Crédito (R$)", min_value=0.0, value=float(st.session_state["credito_valor"]), format="%.2f")
        st.session_state["beneficio_valor"] = m3.number_input("Valor Benefício (R$)", min_value=0.0, value=float(st.session_state["beneficio_valor"]), format="%.2f")
        st.session_state["parcela_consorcio"] = m4.number_input("Parcela Consórcio (R$)", min_value=0.0, value=float(st.session_state["parcela_consorcio"]), format="%.2f")
        st.session_state["num_parcelas_consorcio"] = st.number_input("Nº Parcelas Consórcio", min_value=0, step=1, value=int(st.session_state["num_parcelas_consorcio"]))

        av1, av2 = st.columns(2)
        st.session_state["avalista_nome"] = av1.text_input("Nome do Avalista", value=st.session_state["avalista_nome"])
        st.session_state["avalista_cpf"] = av2.text_input("CPF do Avalista", value=st.session_state["avalista_cpf"])
        av3, av4 = st.columns(2)
        st.session_state["conjuge_avalista_nome"] = av3.text_input("Nome do Cônjuge do Avalista", value=st.session_state["conjuge_avalista_nome"])
        st.session_state["conjuge_avalista_cpf"] = av4.text_input("CPF do Cônjuge do Avalista", value=st.session_state["conjuge_avalista_cpf"])


# ----------------------------------------------------------------------------
# ABA 2: ANÁLISE PRODUTIVA (PRODUÇÃO)
# ----------------------------------------------------------------------------
with aba2:
    st.subheader("🌱 Análise Produtiva e Propriedades do Cliente")
    st.caption("Cadastre aqui 1 ou mais imóveis do produtor. A primeira propriedade representa o Imóvel Beneficiado.")

    props = st.session_state["propriedades_lista"]
    col_add, col_rem = st.columns([1, 1])
    if col_add.button("➕ Adicionar Outra Propriedade"):
        props.append({
            "nome": "", "matricula": "", "num_pes": 0, "espacamento": "",
            "variedades": "", "idade": "", "prev_2027": "",
            "prod_2026": "", "prod_2025": "", "prod_2024": "",
            "venda_2026": 0.0, "venda_2025": 0.0, "venda_2024": 0.0,
        })
        st.rerun()
    if len(props) > 1 and col_rem.button("➖ Remover Última Propriedade"):
        props.pop()
        st.rerun()

    for idx, p in enumerate(props):
        titulo_box = f"🏡 Propriedade 1 (Beneficiada)" if idx == 0 else f"🏡 Propriedade {idx + 1}"
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
    st.session_state["renda_extra_1_desc"] = re1.text_input("Renda Extra 1 (Descrição)", value=st.session_state["renda_extra_1_desc"])
    st.session_state["renda_extra_1_val"] = re2.number_input("Valor Renda 1 (R$)", min_value=0.0, step=500.0, value=float(st.session_state["renda_extra_1_val"]), format="%.2f")
    st.session_state["renda_extra_2_desc"] = re3.text_input("Renda Extra 2 (Descrição)", value=st.session_state["renda_extra_2_desc"])
    st.session_state["renda_extra_2_val"] = re4.number_input("Valor Renda 2 (R$)", min_value=0.0, step=500.0, value=float(st.session_state["renda_extra_2_val"]), format="%.2f")

    st.session_state["bens"] = st.text_area("Relação de Bens (máquinas, veículos, benfeitorias)", value=st.session_state["bens"], height=80)

    resumo_prod = montar_dicionario_proposta()
    st.metric("💵 Renda Bruta Anual Calculada (fórmula aba PRODUÇÃO)", fmt_moeda(resumo_prod["renda_bruta_anual"]))


# ----------------------------------------------------------------------------
# ABA 3: ORDEM DE SERVIÇO & LGPD
# ----------------------------------------------------------------------------
with aba3:
    st.subheader("🧾 Ordem de Serviço (Cálculo Automático de Honorários)")
    st.session_state["descricao_servico"] = st.text_area(
        "Descrição do Serviço (preenchida automaticamente ao escolher o Tipo de Serviço na Aba 1):",
        value=st.session_state["descricao_servico"],
        height=90,
    )

    os1, os2, os3, os4 = st.columns(4)
    opcoes_faixa = {k: v["rotulo"] for k, v in FAIXAS_HONORARIOS.items()}
    st.session_state["faixa_honorario_idx"] = os1.selectbox(
        "Faixa de Honorários (Projeto Técnico)",
        options=list(opcoes_faixa.keys()),
        format_func=lambda k: opcoes_faixa[k],
        index=list(opcoes_faixa.keys()).index(st.session_state["faixa_honorario_idx"]),
    )
    st.session_state["desconto"] = os2.number_input("Desconto (R$)", min_value=0.0, step=100.0, value=float(st.session_state["desconto"]), format="%.2f")
    st.session_state["acrescimos"] = os3.number_input("Acréscimos (R$)", min_value=0.0, step=100.0, value=float(st.session_state["acrescimos"]), format="%.2f")
    st.session_state["num_parcelas"] = os4.number_input("Nº de Parcelas", min_value=1, step=1, value=int(st.session_state["num_parcelas"]))

    st.session_state["forma_pagamento"] = st.text_input("Forma de Pagamento", value=st.session_state["forma_pagamento"])

    d_calc = montar_dicionario_proposta()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valor Proposto", fmt_moeda(d_calc["valor_proposto"]))
    k2.metric("Projeto Técnico (Subtotal)", fmt_moeda(d_calc["valor_projeto_tecnico"]))
    k3.metric("TOTAL DA ORDEM DE SERVIÇO", fmt_moeda(d_calc["valor_total_os"]))
    k4.metric(f"{d_calc['num_parcelas']}x Parcela(s) de", fmt_moeda(d_calc["valor_parcela"]))

    st.divider()
    st.subheader("🔒 Conferência do Termo LGPD (Proteção de Dados)")
    st.info(
        f"**Titular:** {d_calc['cliente_nome'] or '(preencher)'} | **CPF/CNPJ:** {fmt_doc(d_calc['cliente_cpf'])}\n\n"
        f"**Contabilidade:** {d_calc['contabilidade_nome'] or 'Não informada'} "
        f"(CNPJ: {d_calc['contabilidade_cnpj'] or '—'}) | **Banco:** {d_calc['banco_destino']}"
    )

    if st.button("💾 Salvar Proposta e Atualizar Cadastro no Banco", type="primary", use_container_width=True):
        pid = salvar_tudo_no_banco()
        if pid:
            st.success(f"✅ Proposta #{pid} salva com segurança no PostgreSQL! Agora você já pode gerar os PDFs na Aba 4.")


# ----------------------------------------------------------------------------
# ABA 4: GERAR PDFs & PACOTES BANCÁRIOS
# ----------------------------------------------------------------------------
with aba4:
    st.subheader("🖨️ Emissão de Pacote Completo por Banco ou Documento Individual")
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

        st.caption(f"Documentos que entrarão neste PDF ({len(docs_do_pacote)}): " + ", ".join(docs_do_pacote))
        if docs_do_pacote:
            pdf_pacote = gerar_pdf_bytes(d_pdf, docs_do_pacote)
            st.download_button(
                label=f"📥 Baixar Pacote PDF — {banco_pacote}",
                data=pdf_pacote,
                file_name=f"PACOTE_{banco_pacote.replace(' ', '_')}_{nome_arquivo_base}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )

    with col_ind:
        st.markdown("### 📄 Documento Individual (Avulso)")
        doc_avulso = st.selectbox("Escolha qualquer um dos 23 documentos:", TODOS_OS_DOCUMENTOS)
        pdf_avulso = gerar_pdf_bytes(d_pdf, [doc_avulso])
        st.download_button(
            label=f"📥 Baixar PDF Individual — {doc_avulso}",
            data=pdf_avulso,
            file_name=f"{doc_avulso.replace(' ', '_')}_{nome_arquivo_base}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ----------------------------------------------------------------------------
# ABA 5: HISTÓRICO, CONSULTAS, EXCEL E CONTABILIDADES
# ----------------------------------------------------------------------------
with aba5:
    st.subheader("🗂️ Histórico de Propostas Salvas")
    f1, f2, f3 = st.columns([2, 1.5, 1])
    busca_hist = f1.text_input("Filtrar por Nome ou CPF/CNPJ:")
    banco_hist = f2.selectbox("Filtrar por Banco:", ["TODOS"] + listas_cat.get("BANCO", []))
    limite_hist = f3.number_input("Máx. linhas", min_value=20, max_value=2000, value=200, step=50)

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

    st.dataframe(df_hist, use_container_width=True, hide_index=True)

    c_load, c_exp = st.columns([2, 1])
    if not df_hist.empty:
        op_props = {
            f"#{r['id']} | {r['data_proposta']} | {r['cliente']} ({r['banco']} — {fmt_moeda(r['valor_proposto'])})": int(r["id"])
            for _, r in df_hist.iterrows()
        }
        prop_sel = c_load.selectbox("Abrir proposta do histórico para editar ou reimprimir:", list(op_props.keys()))
        if c_load.button("📂 Carregar Proposta Selecionada"):
            carregar_proposta_salva(op_props[prop_sel])
            st.success(f"Proposta #{op_props[prop_sel]} carregada nas abas 1 a 4!")
            st.rerun()

        buf_xlsx = io.BytesIO()
        with pd.ExcelWriter(buf_xlsx, engine="openpyxl") as writer:
            df_hist.to_excel(writer, index=False, sheet_name="Historico_Propostas")
        c_exp.write("")
        c_exp.download_button(
            "📥 Exportar Histórico em Excel (.xlsx)",
            data=buf_xlsx.getvalue(),
            file_name="historico_propostas_regularize.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()
    st.subheader("🏢 Cadastrar Nova Contabilidade")
    with st.form("form_nova_contabilidade", clear_on_submit=True):
        nc1, nc2 = st.columns(2)
        novo_nome_cont = nc1.text_input("Nome do Escritório / Contador")
        novo_cnpj_cont = nc2.text_input("CNPJ (opcional)")
        if st.form_submit_button("➕ Salvar Contabilidade"):
            if novo_nome_cont.strip():
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO contabilidades (nome, cnpj)
                            VALUES (:n, :c)
                            ON CONFLICT (nome) DO UPDATE SET cnpj = EXCLUDED.cnpj
                        """),
                        {"n": novo_nome_cont.strip(), "c": novo_cnpj_cont.strip()},
                    )
                carregar_listas_auxiliares.clear()
                st.success(f"Contabilidade '{novo_nome_cont.strip()}' salva!")
                st.rerun()
            else:
                st.warning("Informe o nome da contabilidade.")
