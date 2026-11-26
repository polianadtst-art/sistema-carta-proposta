# ============================================================================
# ARQUIVO: app.py (Versão 11.0 — Regularize Assessoria Rural)
# O QUE ESTE ARQUIVO FAZ:
#   Sistema web multiusuário em Português do Brasil (PT-BR) conectado ao
#   PostgreSQL (Supabase), com:
#   - Admin Master: regularizeassessoriarural@gmail.com e regularizesulmg@gmail.com
#     (acesso total permanente, protegidos contra desativação/exclusão)
#   - Salvamento Automático ao Trocar de Aba (barra de abas reativa com
#     detecção inteligente de alterações, sem duplicar propostas e sem perder dados)
#   - Gestão de Usuários e Tipos de Autorizações (Aba 6 — somente Admin por senha)
#   - Margem de Crédito Pessoal com caixinhas [ ] para marcar X + Consórcio melhorado
#   - Ordem de Serviço limpa na impressão (Subtotal, % Desconto, sem parcelamento)
#     e painel financeiro espaçoso na tela + liberação pontual de desconto pelo Admin
#   - Análise Produtiva com R$ 0,00 somado ao final e linha inteira para Nome da Propriedade
#   - Município do Banco / Cooperativa (182 cidades num raio de 150 km de Divino - MG)
#   - Busca de CEP multi-provedor (ViaCEP -> BrasilAPI -> OpenCEP) e máscaras CPF/CNPJ
#   - PDFs 100% Preto e Branco, 1 folha A4 equilibrada por documento e marca d'água Regularize
#
#   Você NÃO precisa mexer neste arquivo!
#   - Para alterar dados da empresa/taxas/culturas/linhas/admins: edite config.py
#   - Para alterar senha do banco ou senha mestra: edite Settings -> Secrets no Streamlit
# ============================================================================

import hashlib
import hmac
import io
import json
import re
import secrets
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

from config import (
    ADMIN_MASTER_EMAILS,
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
    MUNICIPIOS_BANCOS_150KM_DIVINO,
    PACOTES_BANCOS,
    PERFIS_AUTORIZACAO,
    PERMISSOES_DESCRICAO,
    TAXA_HONORARIO_CHEIA,
    TIPOS_CLIENTE_PADRAO,
    TIPOS_CREDITO_PESSOAL_PADRAO,
    TIPOS_ENVIO_PADRAO,
    TODOS_OS_DOCUMENTOS,
)
from pdf_generator import fmt_cep, fmt_doc, fmt_input_moeda_br, fmt_moeda, fmt_pct_br, gerar_pdf_bytes, parse_moeda_br

# Fuso horário de Brasília (UTC-3) para exibir horário real do salvamento automático
FUSO_BRASILIA = timezone(timedelta(hours=-3))

# ============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA E ESTILO VISUAL DAS ABAS REATIVAS
# ============================================================================
st.set_page_config(
    page_title=f"Sistema Carta-Proposta | {EMPRESA['nome_fantasia']}",
    page_icon="🌱",
    layout="wide",
)

# Estilo limpo para que a barra de navegação horizontal tenha visual de abas modernas
st.markdown(
    """
    <style>
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        border-bottom: 2px solid #E2E8F0;
        padding-bottom: 8px;
        margin-bottom: 12px;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] label {
        background-color: #F8FAFC;
        border: 1px solid #CBD5E1;
        border-radius: 8px;
        padding: 6px 12px !important;
        cursor: pointer;
        transition: all 0.15s ease;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] label:hover {
        border-color: #166534;
        background-color: #F0FDF4;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] label:has(input:checked) {
        background-color: #166534 !important;
        border-color: #166534 !important;
        color: #FFFFFF !important;
        font-weight: 600;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] label:has(input:checked) p {
        color: #FFFFFF !important;
        font-weight: 600;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] label > div:first-child {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    eng = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    try:
        with eng.begin() as conn:
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS parecer_agencia TEXT DEFAULT ''"))
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS banco_municipio VARCHAR(120) DEFAULT ''"))
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS valor_cheio_os NUMERIC(15,2) DEFAULT 0"))
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS desconto_faixa NUMERIC(15,2) DEFAULT 0"))
            conn.execute(text("ALTER TABLE propostas ADD COLUMN IF NOT EXISTS desconto_extra NUMERIC(15,2) DEFAULT 0"))
            conn.execute(text(
                "INSERT INTO aux_listas_gerais (categoria, valor) VALUES ('CARENCIA', 'SIM (1 ano)') "
                "ON CONFLICT (categoria, valor) DO NOTHING"
            ))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios_sistema (
                    email VARCHAR(180) PRIMARY KEY,
                    nome VARCHAR(180) NOT NULL DEFAULT '',
                    senha_hash VARCHAR(255) NOT NULL,
                    perfil VARCHAR(40) NOT NULL DEFAULT 'ATENDENTE',
                    ativo BOOLEAN NOT NULL DEFAULT TRUE,
                    permissoes JSONB NOT NULL DEFAULT '{}'::jsonb,
                    criado_por VARCHAR(180) DEFAULT 'sistema',
                    criado_em TIMESTAMP DEFAULT NOW(),
                    atualizado_em TIMESTAMP DEFAULT NOW(),
                    ultimo_acesso TIMESTAMP
                )
            """))
            conn.execute(text("ALTER TABLE usuarios_sistema ADD COLUMN IF NOT EXISTS ultimo_acesso TIMESTAMP"))
    except Exception:
        pass

    return eng


engine = conectar_banco()


# ============================================================================
# 3. SEGURANÇA, ADMIN MASTER, USUÁRIOS E AUTORIZAÇÕES POR SENHA
# ============================================================================
def gerar_hash_senha(senha_plana):
    """Gera hash seguro (PBKDF2-HMAC-SHA256 com salt aleatório) para salvar senhas no banco."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", str(senha_plana).encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"pbkdf2_sha256${salt}${dk.hex()}"


def verificar_senha_hash(senha_plana, hash_salvo):
    """Confere a senha digitada contra o hash salvo no banco de dados."""
    if not hash_salvo or not senha_plana:
        return False
    partes = str(hash_salvo).split("$")
    if len(partes) != 3 or partes[0] != "pbkdf2_sha256":
        return hmac.compare_digest(str(senha_plana), str(hash_salvo))
    _, salt, hex_esperado = partes
    dk = hashlib.pbkdf2_hmac("sha256", str(senha_plana).encode("utf-8"), salt.encode("utf-8"), 120000)
    return hmac.compare_digest(dk.hex(), hex_esperado)


def obter_admins_master():
    """Retorna os e-mails de Administradores Master (config.py + Secrets opcional)."""
    admins = {e.strip().lower() for e in ADMIN_MASTER_EMAILS}
    extras = st.secrets.get("ADMIN_EMAILS", [])
    if isinstance(extras, str):
        admins.update(x.strip().lower() for x in extras.split(",") if x.strip())
    elif isinstance(extras, (list, tuple)):
        admins.update(str(x).strip().lower() for x in extras if str(x).strip())
    return admins


def eh_admin_master(email):
    """Verifica se o e-mail informado é um Administrador Master protegido."""
    return str(email or "").strip().lower() in obter_admins_master()


def sincronizar_usuarios_iniciais():
    """
    1. Importa automaticamente os usuários dos Secrets para a tabela usuarios_sistema
       (sem sobrescrever usuários já configurados no banco).
    2. Garante que TODOS os e-mails em ADMIN_MASTER_EMAILS (incluindo
       regularizeassessoriarural@gmail.com) estejam sempre promovidos como ADMIN
       ativo com 100% das permissões, mesmo que já existissem antes como ATENDENTE!
    """
    admins_master = obter_admins_master()
    usuarios_secrets = dict(st.secrets.get("usuarios", {}))
    perms_admin_json = json.dumps(PERFIS_AUTORIZACAO["ADMIN"]["permissoes"], ensure_ascii=False)

    try:
        with engine.begin() as conn:
            # 1. Insere quem ainda não estava na tabela
            for email_raw, senha_raw in usuarios_secrets.items():
                email = str(email_raw).strip().lower()
                if not email:
                    continue
                eh_adm = email in admins_master
                perfil = "ADMIN" if eh_adm else "ATENDENTE"
                perms = dict(PERFIS_AUTORIZACAO[perfil]["permissoes"])
                nome_padrao = email.split("@")[0].replace(".", " ").title()
                conn.execute(
                    text("""
                        INSERT INTO usuarios_sistema (email, nome, senha_hash, perfil, ativo, permissoes, criado_por)
                        VALUES (:email, :nome, :shash, :perfil, TRUE, CAST(:perms AS jsonb), 'migracao_secrets')
                        ON CONFLICT (email) DO NOTHING
                    """),
                    {
                        "email": email,
                        "nome": nome_padrao,
                        "shash": gerar_hash_senha(str(senha_raw)),
                        "perfil": perfil,
                        "perms": json.dumps(perms, ensure_ascii=False),
                    },
                )

            # 2. Promove automaticamente todo Admin Master já existente no banco (ex.: regularizeassessoriarural@gmail.com)
            for email_master in admins_master:
                conn.execute(
                    text("""
                        UPDATE usuarios_sistema
                        SET perfil = 'ADMIN',
                            ativo = TRUE,
                            permissoes = CAST(:perms AS jsonb),
                            atualizado_em = NOW()
                        WHERE LOWER(email) = :e
                          AND (perfil <> 'ADMIN' OR ativo = FALSE OR COALESCE((permissoes->>'gerenciar_usuarios')::boolean, FALSE) = FALSE)
                    """),
                    {"perms": perms_admin_json, "e": email_master},
                )
    except Exception:
        pass


def carregar_usuario_db(email):
    """Busca dados e autorizações atualizadas do usuário no PostgreSQL."""
    e_norm = str(email or "").strip().lower()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT email, nome, senha_hash, perfil, ativo, permissoes
                FROM usuarios_sistema
                WHERE LOWER(email) = :e
            """),
            {"e": e_norm},
        ).mappings().first()
    if not row:
        return None
    eh_master = eh_admin_master(row["email"])
    perfil_efetivo = "ADMIN" if eh_master else row["perfil"]
    if eh_master or perfil_efetivo == "ADMIN":
        perms = dict(PERFIS_AUTORIZACAO["ADMIN"]["permissoes"])
    else:
        perms = dict(PERFIS_AUTORIZACAO.get(perfil_efetivo, PERFIS_AUTORIZACAO["ATENDENTE"])["permissoes"])
        if isinstance(row["permissoes"], dict):
            perms.update({k: bool(v) for k, v in row["permissoes"].items()})
    return {
        "email": row["email"].strip().lower(),
        "nome": row["nome"] or row["email"].split("@")[0].title(),
        "senha_hash": row["senha_hash"],
        "perfil": perfil_efetivo,
        "eh_master": eh_master,
        "ativo": True if eh_master else bool(row["ativo"]),
        "permissoes": perms,
    }


def registrar_atividade_usuario(email, forcar=False):
    """Atualiza o horário de último acesso do usuário no banco (a cada 2 min ou no login)."""
    e_norm = str(email or "").strip().lower()
    if not e_norm:
        return
    agora_ts = datetime.now(timezone.utc).timestamp()
    ultimo_reg = float(st.session_state.get("_ultimo_ping_usuario_ts") or 0.0)
    if (not forcar) and (agora_ts - ultimo_reg < 120):
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE usuarios_sistema SET ultimo_acesso = NOW() WHERE LOWER(email) = :e"),
                {"e": e_norm},
            )
        st.session_state["_ultimo_ping_usuario_ts"] = agora_ts
    except Exception:
        pass


def limpar_cache_form_admin_usuario(email_alvo):
    """Remove chaves temporárias do formulário de edição de um usuário após salvar/alternar status."""
    alvo = str(email_alvo or "").strip().lower()
    for k in list(st.session_state.keys()):
        if alvo and alvo in k and (k.startswith("adm_ed_") or k.startswith("adm_edit_perf_")):
            del st.session_state[k]


def alternar_status_usuario_db(email_alvo, novo_status_ativo):
    """Ativa ou desativa um usuário diretamente no PostgreSQL (protegendo Admin Master e o próprio admin)."""
    e_norm = str(email_alvo or "").strip().lower()
    if eh_admin_master(e_norm):
        return False, "👑 Contas Admin Master não podem ser desativadas."
    if e_norm == str(st.session_state.get("usuario_logado") or "").strip().lower() and not novo_status_ativo:
        return False, "⛔ Você não pode desativar o seu próprio usuário enquanto está logado."
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE usuarios_sistema
                SET ativo = :at, atualizado_em = NOW()
                WHERE LOWER(email) = :e
            """),
            {"at": bool(novo_status_ativo), "e": e_norm},
        )
    limpar_cache_form_admin_usuario(e_norm)
    status_txt = "ATIVADO ✅" if novo_status_ativo else "DESATIVADO ⛔"
    return True, f"Usuário {e_norm} foi {status_txt} com sucesso!"


def validar_senha_admin(senha_digitada):
    """
    Confirma se a senha informada pertence a um Administrador ativo (incluindo os
    Admins Master regularizeassessoriarural@gmail.com e regularizesulmg@gmail.com)
    ou à SENHA_ADMIN configurada nos Secrets.
    """
    if not senha_digitada:
        return False

    # 1. Senha mestra opcional nos Secrets (SENHA_ADMIN = "...")
    senha_mestra = st.secrets.get("SENHA_ADMIN", "")
    if senha_mestra and hmac.compare_digest(str(senha_digitada), str(senha_mestra)):
        return True

    # 2. Senha de qualquer Administrador ativo na tabela usuarios_sistema
    try:
        with engine.connect() as conn:
            admins_db = conn.execute(
                text("""
                    SELECT email, senha_hash, perfil, permissoes
                    FROM usuarios_sistema
                    WHERE ativo = TRUE
                      AND (perfil = 'ADMIN' OR COALESCE((permissoes->>'gerenciar_usuarios')::boolean, FALSE) = TRUE)
                """)
            ).mappings().all()
        for adm in admins_db:
            if verificar_senha_hash(senha_digitada, adm["senha_hash"]):
                return True
    except Exception:
        pass

    # 3. Fallback: senha de qualquer Admin Master nos Secrets
    admins_master = obter_admins_master()
    usuarios_secrets = {k.strip().lower(): str(v) for k, v in dict(st.secrets.get("usuarios", {})).items()}
    for e_adm in admins_master:
        if e_adm in usuarios_secrets and hmac.compare_digest(str(senha_digitada), usuarios_secrets[e_adm]):
            return True

    return False


def tem_permissao(chave):
    """Verifica se o usuário logado possui determinada autorização."""
    if eh_admin_master(st.session_state.get("usuario_logado")):
        return True
    if st.session_state.get("usuario_perfil") == "ADMIN":
        return True
    perms = st.session_state.get("usuario_permissoes") or {}
    return bool(perms.get(chave, False))


def pode_dar_desconto_os():
    """Verdadeiro se o usuário tem autorização de desconto OU se o Admin liberou por senha nesta proposta."""
    return tem_permissao("aplicar_desconto_os") or bool(st.session_state.get("desconto_liberado_por_admin", False))


def verificar_login():
    """Autentica o usuário na tabela usuarios_sistema (sincronizando Secrets e promovendo Admins Master)."""
    if not st.session_state.get("_usuarios_sincronizados"):
        sincronizar_usuarios_iniciais()
        st.session_state["_usuarios_sincronizados"] = True

    if st.session_state.get("usuario_logado"):
        u_live = carregar_usuario_db(st.session_state["usuario_logado"])
        if u_live:
            if not u_live["ativo"]:
                st.session_state.clear()
                st.error("⛔ Seu acesso foi desativado pelo Administrador.")
                st.stop()
            st.session_state["usuario_nome"] = u_live["nome"]
            st.session_state["usuario_perfil"] = u_live["perfil"]
            st.session_state["usuario_permissoes"] = u_live["permissoes"]
        registrar_atividade_usuario(st.session_state["usuario_logado"], forcar=False)
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
                u_db = carregar_usuario_db(email)
                if u_db is not None:
                    if not u_db["ativo"]:
                        st.error("⛔ Usuário desativado. Solicite a liberação ao Administrador.")
                    elif verificar_senha_hash(senha, u_db["senha_hash"]):
                        st.session_state["usuario_logado"] = u_db["email"]
                        st.session_state["usuario_nome"] = u_db["nome"]
                        st.session_state["usuario_perfil"] = u_db["perfil"]
                        st.session_state["usuario_permissoes"] = u_db["permissoes"]
                        registrar_atividade_usuario(u_db["email"], forcar=True)
                        st.rerun()
                    else:
                        st.error("E-mail ou senha incorretos. Verifique com a administração.")
                else:
                    usuarios_permitidos = dict(st.secrets.get("usuarios", {}))
                    mapa_lower = {k.strip().lower(): str(v) for k, v in usuarios_permitidos.items()}
                    if email in mapa_lower and senha == mapa_lower[email]:
                        perf = "ADMIN" if eh_admin_master(email) else "ATENDENTE"
                        st.session_state["usuario_logado"] = email
                        st.session_state["usuario_nome"] = email.split("@")[0].title()
                        st.session_state["usuario_perfil"] = perf
                        st.session_state["usuario_permissoes"] = dict(PERFIS_AUTORIZACAO[perf]["permissoes"])
                        st.rerun()
                    else:
                        st.error("E-mail ou senha incorretos. Verifique com a administração.")
    st.stop()


usuario_atual = verificar_login()


# ============================================================================
# 4. FUNÇÕES AUXILIARES (CPF/CNPJ, CEP MULTI-PROVEDOR E CONVERSÃO LIMPA)
# ============================================================================
def apenas_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def normalizar_espacos(texto):
    return re.sub(r"\s+", " ", str(texto or "").strip())


def chave_alfabetica_ptbr(texto):
    """Chave de ordenação alfabética em Português do Brasil (ignora acentos e maiúsculas)."""
    norm = unicodedata.normalize("NFKD", str(texto or "").strip())
    sem_acento = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return sem_acento.lower()


def ordenar_alfabetico_ptbr(itens, manter_no_fim=()):
    """Ordena uma lista em ordem alfabética A–Z (PT-BR), sem duplicar e mantendo itens especiais no final."""
    finais_upper = {str(x).strip().upper() for x in manter_no_fim}
    vistos = set()
    principais = []
    finais = []
    for item in itens:
        txt = str(item or "").strip()
        if not txt:
            continue
        chave = txt.upper()
        if chave in vistos:
            continue
        vistos.add(chave)
        if chave in finais_upper:
            finais.append(txt)
        else:
            principais.append(txt)
    return sorted(principais, key=chave_alfabetica_ptbr) + sorted(finais, key=chave_alfabetica_ptbr)


def num_float_ou_none(valor):
    if valor is None or str(valor).strip() == "":
        return None
    try:
        v = float(valor)
        return v if abs(v) > 1e-9 else None
    except (TypeError, ValueError):
        return None


def num_int_ou_none(valor):
    if valor is None or str(valor).strip() == "":
        return None
    try:
        v = int(float(valor))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def buscar_cep_online(cep_texto):
    """Consulta o CEP em 3 provedores gratuitos (ViaCEP -> BrasilAPI -> OpenCEP)."""
    dig = apenas_digitos(cep_texto)
    if len(dig) != 8:
        return None

    headers = {"User-Agent": "Mozilla/5.0 (SistemaRegularize/8.0)"}

    for url, modo in [
        (f"https://viacep.com.br/ws/{dig}/json/", "viacep"),
        (f"https://brasilapi.com.br/api/cep/v2/{dig}", "brasilapi"),
        (f"https://opencep.com/v1/{dig}.json", "opencep"),
    ]:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = json.loads(resp.read().decode("utf-8"))
                if modo == "viacep" and not d.get("erro"):
                    return {
                        "cep": fmt_cep(dig),
                        "rua": (d.get("logradouro") or "").strip(),
                        "bairro": (d.get("bairro") or "").strip(),
                        "cidade": (d.get("localidade") or "").strip(),
                        "uf": (d.get("uf") or "").strip().upper(),
                    }
                if modo == "brasilapi" and d.get("city"):
                    return {
                        "cep": fmt_cep(dig),
                        "rua": (d.get("street") or "").strip(),
                        "bairro": (d.get("neighborhood") or "").strip(),
                        "cidade": (d.get("city") or "").strip(),
                        "uf": (d.get("state") or "").strip().upper(),
                    }
                if modo == "opencep" and d.get("localidade"):
                    return {
                        "cep": fmt_cep(dig),
                        "rua": (d.get("logradouro") or "").strip(),
                        "bairro": (d.get("bairro") or "").strip(),
                        "cidade": (d.get("localidade") or "").strip(),
                        "uf": (d.get("uf") or "").strip().upper(),
                    }
        except Exception:
            continue
    return None


@st.cache_data(ttl=60)
def carregar_listas_auxiliares():
    """Carrega contabilidades e listas do PostgreSQL combinadas com o catálogo atualizado."""
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

    catalogo_completo = {k: dict(v) for k, v in CATALOGO_SERVICOS.items()}
    for _, r in df_serv.iterrows():
        s = normalizar_espacos(r["tipo_servico"])
        if s and s not in catalogo_completo:
            catalogo_completo[s] = {
                "linha": normalizar_espacos(r["linha_credito"] or "OUTROS"),
                "descricao": str(r["descricao_servico"] or ""),
                "itens": listas_db.get("ITEM", []),
            }

    def _unir(padrao, extras, manter_no_fim=()):
        combinados = [normalizar_espacos(x) for x in (list(padrao) + list(extras)) if str(x or "").strip()]
        return ordenar_alfabetico_ptbr(combinados, manter_no_fim=manter_no_fim)

    listas_finais = {
        "CARENCIA": _unir(CARENCIAS_PADRAO, listas_db.get("CARENCIA", [])),
        "CULTURA": _unir(CULTURAS_MG, listas_db.get("CULTURA", []), manter_no_fim=("OUTRA CULTURA / ATIVIDADE",)),
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
    """Na Análise Produtiva, todos os campos monetários iniciam vazios (None) — sem 0,00."""
    return {
        "nome": "", "matricula": "", "num_pes": None, "espacamento": "",
        "variedades": "", "idade": "", "prev_2027": "",
        "prod_2026": "", "prod_2025": "", "prod_2024": "",
        "venda_2026": None, "venda_2025": None, "venda_2024": None,
    }


# Lista de campos escalares que têm widgets na tela (separados por prefixo _w_ para
# nunca perder dados ao trocar entre abas no Streamlit!)
CAMPOS_ESCALARES = [
    "local_emissao", "data_proposta", "parceiro", "banco_destino",
    "banco_municipio", "banco_municipio_custom",
    "cliente_cpf", "cliente_nome", "cliente_telefone", "tipo_cliente",
    "cep", "rua", "localidade", "bairro", "cidade", "uf",
    "contabilidade_nome", "imovel_beneficiado_texto",
    "filtro_linha_credito", "tipo_servico", "descricao_servico",
    "item_financiado", "item_financiado_custom", "cultura", "carencia",
    "valor_proposto", "tipo_envio_docs", "data_envio_docs",
    "faixa_honorario_idx", "desconto_extra", "acrescimos", "forma_pagamento",
    "avalista_nome", "avalista_cpf", "conjuge_avalista_nome", "conjuge_avalista_cpf",
    "credito_modalidades", "credito_valor", "parcela_consorcio", "num_parcelas_consorcio",
    "parecer_agencia",
    "renda_extra_1_desc", "renda_extra_1_val",
    "renda_extra_2_desc", "renda_extra_2_val", "bens",
]

# Campos monetários no padrão brasileiro (ex.: 10.000,00; quando vazio fica em branco)
CAMPOS_MONETARIOS_ESCALARES = {
    "valor_proposto",
    "credito_valor",
    "parcela_consorcio",
    "renda_extra_1_val",
    "renda_extra_2_val",
    "desconto_extra",
    "acrescimos",
}


def inicializar_estado_proposta():
    """Inicializa os campos isolados na sessão do usuário atual."""
    padrao = {
        "proposta_id_edicao": None,
        "proposta_criado_por": None,
        "desconto_liberado_por_admin": False,
        "auto_save_ativo": True,
        "_ultimo_hash_salvo": None,
        "_ultimo_autosave_txt": "",
        "_toast_autosave": "",
        "local_emissao": EMPRESA["cidade_padrao"],
        "data_proposta": date.today(),
        "parceiro": EMPRESA["nome_fantasia"],
        "banco_destino": "",
        "banco_municipio": "",
        "banco_municipio_custom": "",
        "cliente_cpf": "",
        "cliente_nome": "",
        "cliente_telefone": "",
        "tipo_cliente": "",
        "cep": "",
        "rua": "",
        "localidade": "",
        "bairro": "",
        "cidade": "",
        "uf": EMPRESA["uf_padrao"],
        "aviso_cep": "",
        "contabilidade_nome": "",
        "contabilidade_cnpj": "",
        "imovel_beneficiado_texto": "",
        "filtro_linha_credito": "TODAS AS LINHAS",
        "tipo_servico": "",
        "descricao_servico": "",
        "item_financiado": "",
        "item_financiado_custom": "",
        "cultura": "",
        "carencia": "",
        "valor_proposto": None,
        "tipo_envio_docs": "",
        "data_envio_docs": "",
        "faixa_honorario_idx": 2,
        "desconto_extra": None,
        "acrescimos": None,
        "forma_pagamento": "Na emissão da minuta",
        "num_parcelas": None,
        "avalista_nome": "",
        "avalista_cpf": "",
        "conjuge_avalista_nome": "",
        "conjuge_avalista_cpf": "",
        "credito_tipo": "",
        "credito_modalidades": [],
        "credito_valor": None,
        "beneficio_valor": None,
        "parcela_consorcio": None,
        "num_parcelas_consorcio": None,
        "parecer_agencia": "",
        "checklist_docs": {},
        "propriedades_lista": [_propriedade_vazia()],
        "semoventes": {
            "vacas_leite": None, "litros_dia": None, "preco_litro": None,
            "boi_corte": None, "novilhas": None, "bezerros": None,
        },
        "renda_extra_1_desc": "",
        "renda_extra_1_val": None,
        "renda_extra_2_desc": "",
        "renda_extra_2_val": None,
        "bens": "",
    }
    for k, v in padrao.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================================
# 5. SINCRONIZAÇÃO DE WIDGETS E SALVAMENTO AUTOMÁTICO AO TROCAR DE ABA
# ============================================================================
def limpar_chaves_widgets():
    """Remove chaves temporárias _w_* para os campos recarregarem do estado principal."""
    for k in list(st.session_state.keys()):
        if k.startswith("_w_"):
            del st.session_state[k]


def definir_campo(chave, valor, atualizar_widget=True):
    """Atualiza o dado principal e, quando permitido, o widget correspondente."""
    if chave in CAMPOS_MONETARIOS_ESCALARES:
        num = parse_moeda_br(valor)
        st.session_state[chave] = num
        val_widget = fmt_input_moeda_br(num)
    else:
        st.session_state[chave] = valor
        val_widget = valor

    if atualizar_widget:
        wk = f"_w_{chave}"
        if wk in st.session_state:
            try:
                st.session_state[wk] = val_widget
            except Exception:
                # Se o widget já foi desenhado nesta execução, mantém o estado principal atualizado sem erro
                pass


def preparar_widget(chave):
    """Garante que o widget _w_<chave> comece com o valor atual sem disparar avisos."""
    wk = f"_w_{chave}"
    if wk not in st.session_state:
        st.session_state[wk] = st.session_state.get(chave)
    return wk


def preparar_widget_moeda(chave):
    """Garante que um campo monetário comece formatado como '10.000,00' ou '' (nunca '0,00')."""
    wk = f"_w_{chave}"
    if wk not in st.session_state:
        st.session_state[wk] = fmt_input_moeda_br(st.session_state.get(chave))
    return wk


def preparar_widget_lista(chave, opcoes):
    """Garante que um selectbox tenha valor válido dentro de opcoes sem avisos."""
    wk = f"_w_{chave}"
    atual = st.session_state.get(chave)
    if atual not in opcoes:
        atual = opcoes[0] if opcoes else ""
        st.session_state[chave] = atual
    if wk not in st.session_state or st.session_state[wk] not in opcoes:
        st.session_state[wk] = atual
    return wk


def cb_sync_campo(chave, formatar_doc=False, formatar_moeda=False):
    """Copia e formata o valor digitado no widget _w_<chave> para o estado principal."""
    wk = f"_w_{chave}"
    if wk in st.session_state:
        val = st.session_state[wk]
        if formatar_doc:
            val = fmt_doc(val)
            st.session_state[wk] = val
            st.session_state[chave] = val
        elif formatar_moeda or chave in CAMPOS_MONETARIOS_ESCALARES:
            num = parse_moeda_br(val)
            st.session_state[chave] = num
            st.session_state[wk] = fmt_input_moeda_br(num)
        else:
            st.session_state[chave] = val


def cb_sync_prop_moeda(idx, pref, campo_p):
    """Formata valores monetários de venda nas propriedades (ex.: 10.000,00; vazio -> '')."""
    wk = f"_w_p_{pref}_{idx}"
    if wk in st.session_state:
        num = parse_moeda_br(st.session_state[wk])
        st.session_state[wk] = fmt_input_moeda_br(num)
        props = st.session_state.get("propriedades_lista", [])
        if 0 <= idx < len(props):
            props[idx][campo_p] = num


def cb_sync_sem_moeda(campo_s):
    """Formata valores monetários de semoventes (ex.: 2,45 ou 10.000,00; vazio -> '')."""
    wk = f"_w_sem_{campo_s}"
    if wk in st.session_state:
        num = parse_moeda_br(st.session_state[wk])
        st.session_state[wk] = fmt_input_moeda_br(num)
        st.session_state.setdefault("semoventes", {})[campo_s] = num


def sincronizar_widgets_para_estado():
    """
    Lê os valores atuais dos widgets (_w_*) para o estado principal ANTES de
    salvar, gerar PDF ou trocar de aba.
    IMPORTANTE: Nunca escreve de volta em st.session_state[wk] aqui, para evitar
    StreamlitWidgetAlreadyInstantiatedError quando chamada no meio da página!
    A formatação visual de volta no campo acontece apenas nos callbacks on_change.
    """
    # 1. Campos escalares
    for campo in CAMPOS_ESCALARES:
        wk = f"_w_{campo}"
        if wk in st.session_state:
            val = st.session_state[wk]
            if campo in ("cliente_cpf", "avalista_cpf", "conjuge_avalista_cpf"):
                st.session_state[campo] = fmt_doc(val)
            elif campo in CAMPOS_MONETARIOS_ESCALARES:
                st.session_state[campo] = parse_moeda_br(val)
            else:
                st.session_state[campo] = val

    # 2. Checklist de Documentos
    chk = st.session_state.get("checklist_docs", {})
    for k in list(st.session_state.keys()):
        if k.startswith("_w_chk_"):
            chave_doc = k[len("_w_chk_"):]
            chk[chave_doc] = bool(st.session_state[k])
    st.session_state["checklist_docs"] = chk

    # 3. Propriedades da Análise Produtiva
    props = st.session_state.get("propriedades_lista", [])
    mapa_prop_campos = {
        "nome": "nome", "mat": "matricula", "pes": "num_pes", "esp": "espacamento",
        "var": "variedades", "id": "idade", "pr27": "prev_2027",
        "p26": "prod_2026", "p25": "prod_2025", "p24": "prod_2024",
        "v26": "venda_2026", "v25": "venda_2025", "v24": "venda_2024",
    }
    for idx, p in enumerate(props):
        for pref, campo_p in mapa_prop_campos.items():
            wk = f"_w_p_{pref}_{idx}"
            if wk in st.session_state:
                if pref in ("v26", "v25", "v24"):
                    p[campo_p] = parse_moeda_br(st.session_state[wk])
                else:
                    p[campo_p] = st.session_state[wk]

    # 4. Semoventes da Análise Produtiva
    sem = st.session_state.get("semoventes", {})
    for campo_s in ("vacas_leite", "litros_dia", "preco_litro", "boi_corte", "novilhas", "bezerros"):
        wk = f"_w_sem_{campo_s}"
        if wk in st.session_state:
            if campo_s == "preco_litro":
                sem[campo_s] = parse_moeda_br(st.session_state[wk])
            else:
                sem[campo_s] = st.session_state[wk]
    st.session_state["semoventes"] = sem


def _calcular_hash_proposta(d):
    """Cria uma assinatura única dos dados atuais para só auto-salvar quando houver alteração real."""
    payload = json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cb_buscar_cep():
    """Consulta o CEP antes de redesenhar a tela e preenche Rua, Bairro, Cidade e UF."""
    sincronizar_widgets_para_estado()
    cep_digitado = st.session_state.get("cep", "")
    dig = apenas_digitos(cep_digitado)
    if len(dig) != 8:
        st.session_state["aviso_cep"] = "erro:Digite um CEP válido com 8 números."
        return

    definir_campo("cep", fmt_cep(dig))
    res = buscar_cep_online(dig)
    if not res:
        st.session_state["aviso_cep"] = "erro:CEP não encontrado nos Correios. Confira os números ou preencha o endereço manualmente."
        return

    definir_campo("cidade", res["cidade"] or st.session_state.get("cidade", ""))
    definir_campo("uf", res["uf"] or st.session_state.get("uf", "MG"))
    definir_campo("bairro", res["bairro"])
    definir_campo("rua", res["rua"])

    if res["rua"]:
        st.session_state["aviso_cep"] = f"ok:Endereço encontrado: {res['rua']} — {res['bairro']} ({res['cidade']}/{res['uf']})."
    else:
        st.session_state["aviso_cep"] = (
            f"info:CEP geral do município ({res['cidade']}/{res['uf']}). Os Correios não vinculam nome de rua a CEPs únicos de cidade — digite a rua ou localidade manualmente."
        )


def cb_limpar_formulario():
    chaves_manter = {
        "usuario_logado", "usuario_nome", "usuario_perfil",
        "usuario_permissoes", "_usuarios_sincronizados", "auto_save_ativo", "admin_painel_liberado",
    }
    for k in list(st.session_state.keys()):
        if k not in chaves_manter:
            del st.session_state[k]
    inicializar_estado_proposta()
    st.session_state["_nav_aba"] = "📋 1. Nova Proposta & Cliente"


def cb_ao_trocar_servico(catalogo):
    """Atualiza automaticamente a Descrição do Serviço e limpa/ajusta o item daquela linha."""
    cb_sync_campo("tipo_servico")
    serv = st.session_state.get("tipo_servico", "")
    info = catalogo.get(serv)
    if info:
        definir_campo("descricao_servico", info.get("descricao", ""))
        itens_linha = info.get("itens", [])
        if st.session_state.get("item_financiado") not in itens_linha:
            definir_campo("item_financiado", "")
    else:
        definir_campo("descricao_servico", "")
        definir_campo("item_financiado", "")


def cb_aplicar_imovel_salvo():
    esc = st.session_state.get("_w_seletor_imovel_salvo", "")
    if esc:
        definir_campo("imovel_beneficiado_texto", esc)


def cb_carregar_cliente(cpf_cnpj):
    """Carrega cliente + propriedades + contabilidade do PostgreSQL."""
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
                       num_pes_cafe AS num_pes,
                       COALESCE(espacamento, '') AS espacamento,
                       COALESCE(variedades, '') AS variedades,
                       COALESCE(idade_lavoura, '') AS idade
                FROM propriedades
                WHERE cliente_cpf_cnpj = :cpf
                ORDER BY id
            """),
            {"cpf": cpf_cnpj},
        ).mappings().all()

    limpar_chaves_widgets()
    st.session_state["cliente_cpf"] = fmt_doc(cli["cpf_cnpj"])
    st.session_state["cliente_nome"] = cli["nome"] or ""
    st.session_state["cliente_telefone"] = cli["telefone"] or ""
    st.session_state["tipo_cliente"] = cli["tipo_cliente"] or ""
    st.session_state["cep"] = fmt_cep(cli["cep"] or "")
    st.session_state["rua"] = cli["rua"] or ""
    st.session_state["localidade"] = cli["localidade"] or ""
    st.session_state["bairro"] = cli["bairro"] or ""
    st.session_state["cidade"] = cli["cidade"] or ""
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
                "num_pes": num_int_ou_none(p["num_pes"]),
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
    limpar_chaves_widgets()
    st.session_state["proposta_id_edicao"] = row["id"]
    st.session_state["proposta_criado_por"] = row.get("criado_por") or ""
    st.session_state["desconto_liberado_por_admin"] = False
    st.session_state["data_proposta"] = row["data_proposta"]
    st.session_state["local_emissao"] = row["local_emissao"] or EMPRESA["cidade_padrao"]
    st.session_state["parceiro"] = row["parceiro"] or EMPRESA["nome_fantasia"]
    st.session_state["banco_destino"] = row["banco_destino"] or ""
    st.session_state["banco_municipio"] = row.get("banco_municipio") or ""
    st.session_state["banco_municipio_custom"] = ""
    st.session_state["imovel_beneficiado_texto"] = row["imovel_beneficiado_texto"] or ""
    st.session_state["filtro_linha_credito"] = "TODAS AS LINHAS"
    st.session_state["tipo_servico"] = row["tipo_servico"] or ""
    st.session_state["descricao_servico"] = row["descricao_servico"] or ""
    st.session_state["item_financiado"] = row["item_financiado"] or ""
    st.session_state["cultura"] = row["cultura"] or ""
    st.session_state["carencia"] = normalizar_espacos(row["carencia"] or "")
    st.session_state["valor_proposto"] = num_float_ou_none(row["valor_proposto"])
    st.session_state["tipo_envio_docs"] = row["tipo_envio_docs"] or ""
    st.session_state["data_envio_docs"] = row["data_envio_docs"] or ""
    st.session_state["faixa_honorario_idx"] = int(row["faixa_honorario_idx"] or 2)
    st.session_state["desconto_extra"] = num_float_ou_none(row.get("desconto_extra"))
    st.session_state["acrescimos"] = num_float_ou_none(row["acrescimos"])
    st.session_state["forma_pagamento"] = row["forma_pagamento"] or ""
    st.session_state["num_parcelas"] = num_int_ou_none(row["num_parcelas"])
    st.session_state["avalista_nome"] = row["avalista_nome"] or ""
    st.session_state["avalista_cpf"] = fmt_doc(row["avalista_cpf"] or "")
    st.session_state["conjuge_avalista_nome"] = row["conjuge_avalista_nome"] or ""
    st.session_state["conjuge_avalista_cpf"] = fmt_doc(row["conjuge_avalista_cpf"] or "")
    cred_str = row["credito_tipo"] or ""
    st.session_state["credito_tipo"] = cred_str
    mods_lidas = [m.strip().upper() for m in cred_str.split(",") if m.strip()]
    st.session_state["credito_modalidades"] = [m for m in TIPOS_CREDITO_PESSOAL_PADRAO if m in mods_lidas]
    st.session_state["credito_valor"] = num_float_ou_none(row["credito_valor"])
    st.session_state["beneficio_valor"] = num_float_ou_none(row["beneficio_valor"])
    st.session_state["parcela_consorcio"] = num_float_ou_none(row["parcela_consorcio"])
    st.session_state["num_parcelas_consorcio"] = num_int_ou_none(row["num_parcelas_consorcio"])
    st.session_state["parecer_agencia"] = row.get("parecer_agencia") or ""
    st.session_state["checklist_docs"] = dict(row["checklist_docs"] or {})

    prod = dict(row["dados_producao"] or {})
    if prod.get("propriedades"):
        props_limpas = []
        for p in prod["propriedades"]:
            pc = _propriedade_vazia()
            pc.update(p)
            pc["num_pes"] = num_int_ou_none(pc.get("num_pes"))
            pc["venda_2026"] = parse_moeda_br(pc.get("venda_2026"))
            pc["venda_2025"] = parse_moeda_br(pc.get("venda_2025"))
            pc["venda_2024"] = parse_moeda_br(pc.get("venda_2024"))
            props_limpas.append(pc)
        st.session_state["propriedades_lista"] = props_limpas
    if prod.get("semoventes"):
        s_raw = prod["semoventes"]
        st.session_state["semoventes"] = {
            "vacas_leite": num_int_ou_none(s_raw.get("vacas_leite")),
            "litros_dia": num_float_ou_none(s_raw.get("litros_dia")),
            "preco_litro": parse_moeda_br(s_raw.get("preco_litro")),
            "boi_corte": num_int_ou_none(s_raw.get("boi_corte")),
            "novilhas": num_int_ou_none(s_raw.get("novilhas")),
            "bezerros": num_int_ou_none(s_raw.get("bezerros")),
        }
    st.session_state["renda_extra_1_desc"] = prod.get("renda_extra_1_desc", "")
    st.session_state["renda_extra_1_val"] = parse_moeda_br(prod.get("renda_extra_1_val"))
    st.session_state["renda_extra_2_desc"] = prod.get("renda_extra_2_desc", "")
    st.session_state["renda_extra_2_val"] = parse_moeda_br(prod.get("renda_extra_2_val"))
    st.session_state["bens"] = prod.get("bens", "")

    # Marca o estado carregado como já salvo (evita gravação desnecessária antes de editar)
    st.session_state["_ultimo_hash_salvo"] = _calcular_hash_proposta(montar_dicionario_proposta())
    st.session_state["_nav_aba"] = "📋 1. Nova Proposta & Cliente"


# ============================================================================
# 6. CÁLCULOS FINANCEIROS E SALVAMENTO (MANUAL + AUTOMÁTICO AO TROCAR DE ABA)
# ============================================================================
def montar_dicionario_proposta():
    """Calcula Honorários Cheios (2,00%), Desconto da Faixa, Total OS e Renda Bruta."""
    idx_faixa = int(st.session_state.get("faixa_honorario_idx", 2))
    info_faixa = FAIXAS_HONORARIOS.get(idx_faixa, FAIXAS_HONORARIOS[2])
    pct_final = float(info_faixa["percentual"])
    pct_desc_faixa = max(0.0, round(TAXA_HONORARIO_CHEIA - pct_final, 6))

    val_prop = parse_moeda_br(st.session_state.get("valor_proposto")) or 0.0
    tem_valor = val_prop > 0
    valor_cheio_os = round(val_prop * TAXA_HONORARIO_CHEIA, 2) if tem_valor else 0.0
    desconto_faixa = round(val_prop * pct_desc_faixa, 2) if tem_valor else 0.0
    desconto_extra = parse_moeda_br(st.session_state.get("desconto_extra")) or 0.0
    desconto_total = round(desconto_faixa + desconto_extra, 2)
    acresc = parse_moeda_br(st.session_state.get("acrescimos")) or 0.0

    total_os = max(0.0, round(valor_cheio_os - desconto_total + acresc, 2)) if (tem_valor or acresc > 0) else 0.0
    n_parc = num_int_ou_none(st.session_state.get("num_parcelas"))
    val_parc = round(total_os / n_parc, 2) if (n_parc and total_os > 0) else 0.0

    props = st.session_state.get("propriedades_lista") or []
    soma_vendas = round(sum((parse_moeda_br(p.get("venda_2026")) or 0.0) for p in props), 2)
    re1_v = parse_moeda_br(st.session_state.get("renda_extra_1_val")) or 0.0
    re2_v = parse_moeda_br(st.session_state.get("renda_extra_2_val")) or 0.0
    soma_rendas_extras = round(re1_v + re2_v, 2)
    renda_bruta = round(soma_vendas + soma_rendas_extras, 2)

    item_sel = st.session_state.get("item_financiado", "")
    if item_sel == "OUTRO ITEM (DIGITAR MANUALMENTE)":
        item_final = st.session_state.get("item_financiado_custom", "").strip().upper()
    else:
        item_final = item_sel

    mun_banco_sel = st.session_state.get("banco_municipio", "")
    if mun_banco_sel == "OUTRO MUNICÍPIO (DIGITAR MANUALMENTE)":
        banco_municipio_final = st.session_state.get("banco_municipio_custom", "").strip()
    else:
        banco_municipio_final = mun_banco_sel

    mods_sel = st.session_state.get("credito_modalidades") or []
    credito_tipo_final = ", ".join(mods_sel) if mods_sel else st.session_state.get("credito_tipo", "")

    return {
        "local_emissao": st.session_state["local_emissao"],
        "data_proposta": st.session_state["data_proposta"],
        "parceiro": st.session_state["parceiro"],
        "banco_destino": st.session_state["banco_destino"],
        "banco_municipio": banco_municipio_final,
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
        "valor_proposto": val_prop if tem_valor else None,
        "tipo_envio_docs": st.session_state["tipo_envio_docs"],
        "data_envio_docs": st.session_state["data_envio_docs"],
        "faixa_honorario_idx": idx_faixa,
        "percentual_honorario": pct_final,
        "percentual_desconto_faixa": pct_desc_faixa,
        "valor_cheio_os": valor_cheio_os if tem_valor else None,
        "valor_projeto_tecnico": valor_cheio_os if tem_valor else None,
        "desconto_faixa": desconto_faixa if desconto_faixa > 0 else None,
        "desconto_extra": desconto_extra if desconto_extra > 0 else None,
        "desconto": desconto_total if desconto_total > 0 else None,
        "acrescimos": acresc if acresc > 0 else None,
        "valor_total_os": total_os if (tem_valor or acresc > 0) else None,
        "forma_pagamento": st.session_state["forma_pagamento"],
        "num_parcelas": n_parc,
        "valor_parcela": val_parc if val_parc > 0 else None,
        "avalista_nome": st.session_state["avalista_nome"].strip().upper(),
        "avalista_cpf": apenas_digitos(st.session_state["avalista_cpf"]),
        "conjuge_avalista_nome": st.session_state["conjuge_avalista_nome"].strip().upper(),
        "conjuge_avalista_cpf": apenas_digitos(st.session_state["conjuge_avalista_cpf"]),
        "credito_tipo": credito_tipo_final,
        "credito_valor": parse_moeda_br(st.session_state.get("credito_valor")),
        "beneficio_valor": parse_moeda_br(st.session_state.get("beneficio_valor")),
        "parcela_consorcio": parse_moeda_br(st.session_state.get("parcela_consorcio")),
        "num_parcelas_consorcio": num_int_ou_none(st.session_state.get("num_parcelas_consorcio")),
        "parecer_agencia": st.session_state.get("parecer_agencia", "").strip(),
        "checklist_docs": st.session_state.get("checklist_docs", {}),
        "dados_producao": {
            "propriedades": props,
            "semoventes": st.session_state.get("semoventes", {}),
            "renda_extra_1_desc": st.session_state.get("renda_extra_1_desc", ""),
            "renda_extra_1_val": parse_moeda_br(st.session_state.get("renda_extra_1_val")),
            "renda_extra_2_desc": st.session_state.get("renda_extra_2_desc", ""),
            "renda_extra_2_val": parse_moeda_br(st.session_state.get("renda_extra_2_val")),
            "bens": st.session_state.get("bens", ""),
        },
        "soma_vendas_2026": soma_vendas if soma_vendas > 0 else None,
        "soma_rendas_extras": soma_rendas_extras if soma_rendas_extras > 0 else None,
        "renda_bruta_anual": renda_bruta if renda_bruta > 0 else None,
    }


def salvar_tudo_no_banco(silencioso=False):
    """Salva Cliente, Propriedades e Proposta de forma atômica no PostgreSQL."""
    sincronizar_widgets_para_estado()

    if not tem_permissao("criar_editar_proposta"):
        if not silencioso:
            st.error("⛔ Seu usuário tem autorização apenas de consulta. Solicite ao Administrador para liberar gravação.")
        return None

    pid_edit_check = st.session_state.get("proposta_id_edicao")
    dono_prop = str(st.session_state.get("proposta_criado_por") or "").strip().lower()
    if pid_edit_check and dono_prop and dono_prop != usuario_atual and not tem_permissao("editar_proposta_outros"):
        if not silencioso:
            st.error(f"⛔ Esta proposta pertence a '{dono_prop}'. Você não tem autorização para editar propostas de outros atendentes.")
        return None

    if not pode_dar_desconto_os():
        definir_campo("faixa_honorario_idx", 2, atualizar_widget=False)
        definir_campo("desconto_extra", None, atualizar_widget=False)

    d = montar_dicionario_proposta()
    if len(d["cliente_cpf"]) not in (11, 14):
        if not silencioso:
            st.error("❌ Informe um CPF (11 números) ou CNPJ (14 números) válido antes de salvar.")
        return None
    if not d["cliente_nome"]:
        if not silencioso:
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
                    "pes": num_int_ou_none(p.get("num_pes")),
                    "esp": str(p.get("espacamento") or ""),
                    "var": str(p.get("variedades") or ""),
                    "idade": str(p.get("idade") or ""),
                },
            ).first()
            if idx == 0 and res_p:
                prop_benef_id = res_p[0]

        params_prop = {
            "data_proposta": d["data_proposta"] or date.today(),
            "local_emissao": d["local_emissao"],
            "parceiro": d["parceiro"],
            "banco_destino": d["banco_destino"],
            "banco_municipio": d["banco_municipio"],
            "cliente_cpf_cnpj": d["cliente_cpf"],
            "propriedade_beneficiada_id": prop_benef_id,
            "imovel_beneficiado_texto": d["imovel_beneficiado_texto"],
            "tipo_servico": d["tipo_servico"],
            "descricao_servico": d["descricao_servico"],
            "item_financiado": d["item_financiado"],
            "cultura": d["cultura"],
            "carencia": d["carencia"],
            "valor_proposto": float(d["valor_proposto"] or 0),
            "tipo_envio_docs": d["tipo_envio_docs"],
            "data_envio_docs": d["data_envio_docs"],
            "faixa_honorario_idx": d["faixa_honorario_idx"],
            "percentual_honorario": d["percentual_honorario"],
            "valor_cheio_os": float(d["valor_cheio_os"] or 0),
            "valor_projeto_tecnico": float(d["valor_cheio_os"] or 0),
            "desconto_faixa": float(d["desconto_faixa"] or 0),
            "desconto_extra": float(d["desconto_extra"] or 0),
            "desconto": float(d["desconto"] or 0),
            "acrescimos": float(d["acrescimos"] or 0),
            "valor_total_os": float(d["valor_total_os"] or 0),
            "forma_pagamento": d["forma_pagamento"],
            "num_parcelas": int(d["num_parcelas"] or 0),
            "valor_parcela": float(d["valor_parcela"] or 0),
            "avalista_nome": d["avalista_nome"],
            "avalista_cpf": d["avalista_cpf"],
            "conjuge_avalista_nome": d["conjuge_avalista_nome"],
            "conjuge_avalista_cpf": d["conjuge_avalista_cpf"],
            "credito_tipo": d["credito_tipo"],
            "credito_valor": float(d["credito_valor"] or 0),
            "beneficio_valor": float(d["beneficio_valor"] or 0),
            "parcela_consorcio": float(d["parcela_consorcio"] or 0),
            "num_parcelas_consorcio": int(d["num_parcelas_consorcio"] or 0),
            "parecer_agencia": d["parecer_agencia"],
            "checklist_docs": json.dumps(d["checklist_docs"], ensure_ascii=False),
            "dados_producao": json.dumps(d["dados_producao"], ensure_ascii=False),
            "renda_bruta_anual": float(d["renda_bruta_anual"] or 0),
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
                        banco_municipio = :banco_municipio,
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
            pid_final = pid_edit
        else:
            pid_final = conn.execute(
                text("""
                    INSERT INTO propostas (
                        data_proposta, local_emissao, parceiro, banco_destino, banco_municipio,
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
                        :data_proposta, :local_emissao, :parceiro, :banco_destino, :banco_municipio,
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
            st.session_state["proposta_id_edicao"] = pid_final
            st.session_state["proposta_criado_por"] = usuario_atual

    st.session_state["_ultimo_hash_salvo"] = _calcular_hash_proposta(d)
    hora_agora = datetime.now(FUSO_BRASILIA).strftime("%H:%M:%S")
    st.session_state["_ultimo_autosave_txt"] = f"Proposta #{pid_final} salva às {hora_agora}"
    return pid_final


def cb_trocar_aba():
    """
    MECANISMO DE SALVAMENTO AUTOMÁTICO AO TROCAR DE ABA:
    1. Sincroniza todos os campos digitados na aba que o usuário acabou de sair.
    2. Se o salvamento automático estiver ativado, o usuário tiver permissão,
       Nome + CPF/CNPJ válidos estiverem preenchidos e houver alteração real
       desde a última gravação, salva automaticamente no PostgreSQL!
    """
    sincronizar_widgets_para_estado()

    if not st.session_state.get("auto_save_ativo", True):
        return
    if not tem_permissao("criar_editar_proposta"):
        return

    d_atual = montar_dicionario_proposta()
    if len(d_atual["cliente_cpf"]) not in (11, 14) or not d_atual["cliente_nome"]:
        return

    hash_atual = _calcular_hash_proposta(d_atual)
    if hash_atual == st.session_state.get("_ultimo_hash_salvo"):
        return

    try:
        pid = salvar_tudo_no_banco(silencioso=True)
        if pid:
            hora_agora = datetime.now(FUSO_BRASILIA).strftime("%H:%M:%S")
            msg = f"💾 Salvo automaticamente às {hora_agora} (Proposta #{pid})"
            st.session_state["_toast_autosave"] = msg
            st.session_state["_ultimo_autosave_txt"] = f"Auto-salvo às {hora_agora} (Proposta #{pid})"
    except Exception as exc:
        st.session_state["_toast_autosave"] = f"⚠️ Aviso no salvamento automático: {exc}"


# ============================================================================
# 7. INICIALIZAÇÃO, BARRA LATERAL E BARRA DE ABAS REATIVA
# ============================================================================
inicializar_estado_proposta()
catalogo_servicos, listas_cat, df_contabilidades = carregar_listas_auxiliares()

# Exibe notificação discreta quando o salvamento automático acabou de acontecer
if st.session_state.get("_toast_autosave"):
    st.toast(st.session_state["_toast_autosave"])
    st.session_state["_toast_autosave"] = ""

with st.sidebar:
    st.markdown(f"### 🌱 {EMPRESA['nome_fantasia']}")
    nome_exib_user = st.session_state.get("usuario_nome") or usuario_atual
    perfil_exib_user = st.session_state.get("usuario_perfil", "ATENDENTE")
    eh_master_atual = eh_admin_master(usuario_atual)
    st.caption(f"👤 **{nome_exib_user}** ({usuario_atual})")
    if eh_master_atual:
        st.caption("👑 Perfil: **ADMIN MASTER**")
    else:
        st.caption(f"🛡️ Perfil: **{perfil_exib_user}**")

    if st.session_state.get("proposta_id_edicao"):
        st.info(f"✏️ Editando Proposta **#{st.session_state['proposta_id_edicao']}**")
    else:
        st.success("🆕 Nova Proposta")

    st.button("🆕 Limpar / Nova Proposta", on_click=cb_limpar_formulario, use_container_width=True)

    if tem_permissao("criar_editar_proposta"):
        if st.button("💾 Salvar Proposta Agora", type="primary", use_container_width=True):
            pid = salvar_tudo_no_banco(silencioso=False)
            if pid:
                st.success(f"✅ Proposta #{pid} salva com sucesso!")

        st.toggle(
            "🔄 Salvar automaticamente ao trocar de aba",
            key="auto_save_ativo",
            help="Quando ativado, ao clicar em qualquer outra aba o sistema grava automaticamente as alterações no banco de dados (desde que Nome e CPF/CNPJ estejam preenchidos).",
        )
        if st.session_state.get("_ultimo_autosave_txt"):
            st.caption(f"🕒 {st.session_state['_ultimo_autosave_txt']}")
        elif st.session_state.get("auto_save_ativo"):
            st.caption("🕒 Salvamento automático ativo (preencha Nome + CPF/CNPJ).")
    else:
        st.warning("🔒 Modo Somente Consulta")

    st.divider()
    if st.button("🚪 Sair do Sistema", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# ============================================================================
# 8. NAVEGAÇÃO PRINCIPAL POR ABAS REATIVAS (COM SALVAMENTO AUTOMÁTICO)
# ============================================================================
titulos_abas = [
    "📋 1. Nova Proposta & Cliente",
    "🌱 2. Análise Produtiva",
    "🧾 3. Ordem de Serviço & LGPD",
    "🖨️ 4. Imprimir / PDFs (P&B)",
    "🗂️ 5. Histórico & Cadastros",
]
eh_admin_painel = tem_permissao("gerenciar_usuarios")
if eh_admin_painel:
    titulos_abas.append("🔐 6. Administração (Usuários)")

if "_nav_aba" not in st.session_state or st.session_state["_nav_aba"] not in titulos_abas:
    st.session_state["_nav_aba"] = titulos_abas[0]

aba_ativa = st.radio(
    "Navegação do Sistema",
    options=titulos_abas,
    horizontal=True,
    label_visibility="collapsed",
    key="_nav_aba",
    on_change=cb_trocar_aba,
)


# ----------------------------------------------------------------------------
# ABA 1: NOVA PROPOSTA & CADASTRO DO CLIENTE
# ----------------------------------------------------------------------------
if aba_ativa == "📋 1. Nova Proposta & Cliente":
    st.subheader("🔍 Pesquisar Cliente Cadastrado")
    termo_cli = st.text_input(
        "Digite parte do Nome ou CPF/CNPJ para carregar dados e imóveis salvos:",
        placeholder="",
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
                f"{r['nome']} | {fmt_doc(r['cpf_cnpj'])} {('(' + r['cidade'] + ')') if r['cidade'] else ''}".strip(): r["cpf_cnpj"]
                for _, r in df_encontrados.iterrows()
            }
            chaves_cli_ord = ordenar_alfabetico_ptbr(list(opcoes_cli.keys()))
            escolhido = st.selectbox("Selecione o cliente encontrado:", chaves_cli_ord)
            st.button(
                "📥 Carregar Dados e Imóveis deste Cliente",
                on_click=cb_carregar_cliente,
                args=(opcoes_cli[escolhido],),
            )
        else:
            st.caption("Nenhum cliente encontrado com esse termo. Preencha os campos abaixo para cadastrar.")

    st.divider()
    st.subheader("📄 Dados da Proposta e do Produtor")

    c1, c2, c3 = st.columns([1.2, 1.0, 1.8])
    c1.text_input("Local de Emissão", key=preparar_widget("local_emissao"), on_change=cb_sync_campo, args=("local_emissao",))
    c2.date_input("Data da Proposta", key=preparar_widget("data_proposta"), format="DD/MM/YYYY", on_change=cb_sync_campo, args=("data_proposta",))
    c3.text_input("Parceiro / Escritório", key=preparar_widget("parceiro"), on_change=cb_sync_campo, args=("parceiro",))

    b1, b2 = st.columns([1.4, 2.6])
    bancos_raw = list(listas_cat["BANCO"])
    if st.session_state["banco_destino"]:
        bancos_raw.append(st.session_state["banco_destino"])
    bancos_lista = [""] + ordenar_alfabetico_ptbr(bancos_raw)
    b1.selectbox(
        "Banco / Cooperativa de Destino",
        bancos_lista,
        key=preparar_widget_lista("banco_destino", bancos_lista),
        on_change=cb_sync_campo,
        args=("banco_destino",),
    )

    muns_raw = list(MUNICIPIOS_BANCOS_150KM_DIVINO)
    if st.session_state["banco_municipio"] and st.session_state["banco_municipio"] != "OUTRO MUNICÍPIO (DIGITAR MANUALMENTE)":
        muns_raw.append(st.session_state["banco_municipio"])
    opcoes_mun_banco = [""] + ordenar_alfabetico_ptbr(muns_raw) + ["OUTRO MUNICÍPIO (DIGITAR MANUALMENTE)"]
    b2.selectbox(
        "Município do Banco / Cooperativa (raio de 150 km de Divino - MG)",
        opcoes_mun_banco,
        key=preparar_widget_lista("banco_municipio", opcoes_mun_banco),
        on_change=cb_sync_campo,
        args=("banco_municipio",),
        help="Digite o nome da cidade para buscar rapidamente entre os 182 municípios de MG, ES e RJ num raio de 150 km de Divino - MG.",
    )
    if st.session_state["banco_municipio"] == "OUTRO MUNICÍPIO (DIGITAR MANUALMENTE)":
        b2.text_input(
            "Digite o Município e UF do Banco / Cooperativa:",
            key=preparar_widget("banco_municipio_custom"),
            on_change=cb_sync_campo,
            args=("banco_municipio_custom",),
            placeholder="Ex.: Juiz de Fora - MG",
        )

    p1, p2, p3, p4 = st.columns([2.2, 1.4, 1.2, 1.2])
    p1.text_input("Nome Completo do Produtor *", key=preparar_widget("cliente_nome"), on_change=cb_sync_campo, args=("cliente_nome",))
    p2.text_input(
        "CPF ou CNPJ *",
        key=preparar_widget("cliente_cpf"),
        help="Digite apenas números e aperte Enter/Tab: os pontos, traço e barra entram automaticamente.",
        on_change=cb_sync_campo,
        args=("cliente_cpf", True),
    )
    p3.text_input("Telefone / WhatsApp", key=preparar_widget("cliente_telefone"), on_change=cb_sync_campo, args=("cliente_telefone",))
    tcli_raw = list(listas_cat["TIPO_CLIENTE"])
    if st.session_state["tipo_cliente"]:
        tcli_raw.append(st.session_state["tipo_cliente"])
    tipos_cli = [""] + ordenar_alfabetico_ptbr(tcli_raw)
    p4.selectbox(
        "Tipo de Cliente",
        tipos_cli,
        key=preparar_widget_lista("tipo_cliente", tipos_cli),
        on_change=cb_sync_campo,
        args=("tipo_cliente",),
    )

    # Endereço com busca automática de CEP
    e1, e_btn, e2, e3 = st.columns([1.2, 0.9, 2.5, 1.4])
    e1.text_input("CEP", key=preparar_widget("cep"), on_change=cb_sync_campo, args=("cep",))
    e_btn.write("")
    e_btn.write("")
    e_btn.button("🔎 Buscar CEP", on_click=cb_buscar_cep, use_container_width=True)
    e2.text_input("Rua / Logradouro", key=preparar_widget("rua"), on_change=cb_sync_campo, args=("rua",))
    e3.text_input("Localidade / Comunidade", key=preparar_widget("localidade"), on_change=cb_sync_campo, args=("localidade",))

    aviso_cep = st.session_state.get("aviso_cep", "")
    if aviso_cep.startswith("ok:"):
        st.success(aviso_cep[3:])
    elif aviso_cep.startswith("info:"):
        st.info(aviso_cep[5:])
    elif aviso_cep.startswith("erro:"):
        st.warning(aviso_cep[5:])

    e4, e5, e6 = st.columns([2, 2, 0.8])
    e4.text_input("Bairro", key=preparar_widget("bairro"), on_change=cb_sync_campo, args=("bairro",))
    e5.text_input("Cidade", key=preparar_widget("cidade"), on_change=cb_sync_campo, args=("cidade",))
    e6.text_input("UF", key=preparar_widget("uf"), max_chars=2, on_change=cb_sync_campo, args=("uf",))

    # Imóvel Beneficiado
    props_atuais = st.session_state.get("propriedades_lista", [])
    opcoes_imov = ordenar_alfabetico_ptbr([
        f"{p['nome']} Mat {p['matricula']}".strip() if p.get("matricula") else p.get("nome", "")
        for p in props_atuais if p.get("nome")
    ])
    im1, im2 = st.columns([2, 1.5])
    im1.text_input(
        "Imóvel Beneficiado (Nome + Matrícula)",
        key=preparar_widget("imovel_beneficiado_texto"),
        on_change=cb_sync_campo,
        args=("imovel_beneficiado_texto",),
    )
    if opcoes_imov:
        im2.selectbox(
            "Ou selecionar imóvel salvo do cliente:",
            [""] + opcoes_imov,
            key="_w_seletor_imovel_salvo",
            on_change=cb_aplicar_imovel_salvo,
        )

    # OPERAÇÃO DE CRÉDITO
    st.markdown("#### 💰 Operação de Crédito, Linha, Itens Financiáveis e Culturas (MG)")

    linhas_disponiveis = ["TODAS AS LINHAS"] + ordenar_alfabetico_ptbr({v["linha"] for v in catalogo_servicos.values()})
    fl1, fl2 = st.columns([1.2, 2.8])
    fl1.selectbox(
        "Filtrar por Linha de Crédito",
        linhas_disponiveis,
        key=preparar_widget_lista("filtro_linha_credito", linhas_disponiveis),
        on_change=cb_sync_campo,
        args=("filtro_linha_credito",),
    )
    linha_filtro = st.session_state["filtro_linha_credito"]

    if linha_filtro == "TODAS AS LINHAS":
        servicos_filtrados = [""] + ordenar_alfabetico_ptbr(list(catalogo_servicos.keys()))
    else:
        servicos_filtrados = [""] + ordenar_alfabetico_ptbr([k for k, v in catalogo_servicos.items() if v["linha"] == linha_filtro])

    if st.session_state["tipo_servico"] not in servicos_filtrados:
        definir_campo("tipo_servico", "")
        definir_campo("descricao_servico", "")
        definir_campo("item_financiado", "")

    fl2.selectbox(
        "Linha + Tipo de Serviço (preenche a descrição da Ordem de Serviço automaticamente)",
        servicos_filtrados,
        key=preparar_widget_lista("tipo_servico", servicos_filtrados),
        on_change=cb_ao_trocar_servico,
        args=(catalogo_servicos,),
    )

    op1, op2, op3 = st.columns(3)
    info_serv_atual = catalogo_servicos.get(st.session_state["tipo_servico"], {})
    itens_da_linha = list(info_serv_atual.get("itens", [])) if info_serv_atual else list(listas_cat["TODOS_ITENS"])
    if st.session_state["item_financiado"] and st.session_state["item_financiado"] != "OUTRO ITEM (DIGITAR MANUALMENTE)":
        itens_da_linha.append(st.session_state["item_financiado"])
    opcoes_item = [""] + ordenar_alfabetico_ptbr(itens_da_linha) + ["OUTRO ITEM (DIGITAR MANUALMENTE)"]

    op1.selectbox(
        "Item Financiável desta Linha",
        opcoes_item,
        key=preparar_widget_lista("item_financiado", opcoes_item),
        on_change=cb_sync_campo,
        args=("item_financiado",),
    )
    if st.session_state["item_financiado"] == "OUTRO ITEM (DIGITAR MANUALMENTE)":
        op1.text_input(
            "Digite o item financiado:",
            key=preparar_widget("item_financiado_custom"),
            on_change=cb_sync_campo,
            args=("item_financiado_custom",),
        )

    cult_raw = list(listas_cat["CULTURA"])
    if st.session_state["cultura"]:
        cult_raw.append(st.session_state["cultura"])
    lista_cult = [""] + ordenar_alfabetico_ptbr(cult_raw, manter_no_fim=("OUTRA CULTURA / ATIVIDADE",))
    op2.selectbox(
        "Cultura / Atividade Principal (Minas Gerais)",
        lista_cult,
        key=preparar_widget_lista("cultura", lista_cult),
        on_change=cb_sync_campo,
        args=("cultura",),
    )

    car_raw = list(listas_cat["CARENCIA"])
    if st.session_state["carencia"]:
        car_raw.append(st.session_state["carencia"])
    lista_car = [""] + ordenar_alfabetico_ptbr(car_raw)
    op3.selectbox(
        "Carência",
        lista_car,
        key=preparar_widget_lista("carencia", lista_car),
        on_change=cb_sync_campo,
        args=("carencia",),
    )

    op4, op5 = st.columns(2)
    op4.text_input(
        "Valor Proposto (R$)",
        key=preparar_widget_moeda("valor_proposto"),
        on_change=cb_sync_campo,
        args=("valor_proposto", False, True),
        placeholder="Ex.: 10.000,00",
        help="Digite o valor e aperte Enter ou Tab para formatar automaticamente no padrão 10.000,00.",
    )

    cont_raw = df_contabilidades["nome"].tolist()
    mapa_cnpj = dict(zip(df_contabilidades["nome"], df_contabilidades["cnpj"]))
    if st.session_state["contabilidade_nome"]:
        cont_raw.append(st.session_state["contabilidade_nome"])
    nomes_cont = [""] + ordenar_alfabetico_ptbr(cont_raw)
    op5.selectbox(
        "Contabilidade do Produtor",
        nomes_cont,
        key=preparar_widget_lista("contabilidade_nome", nomes_cont),
        on_change=cb_sync_campo,
        args=("contabilidade_nome",),
    )
    st.session_state["contabilidade_cnpj"] = fmt_doc(mapa_cnpj.get(st.session_state["contabilidade_nome"], ""))

    # Checklist de Documentos
    st.markdown("#### ✅ Checklist de Documentos")
    chk = st.session_state.get("checklist_docs", {})
    ck1, ck2, ck3 = st.columns(3)
    with ck1:
        st.caption("**PROPONENTE**")
        for doc_nome in DOCS_PROPONENTE:
            chave = f"prop_{doc_nome}"
            wk = f"_w_chk_{chave}"
            if wk not in st.session_state:
                st.session_state[wk] = bool(chk.get(chave, False))
            chk[chave] = st.checkbox(doc_nome, key=wk)
    with ck2:
        st.caption("**IMÓVEL**")
        for doc_nome in DOCS_IMOVEL:
            chave = f"imov_{doc_nome}"
            wk = f"_w_chk_{chave}"
            if wk not in st.session_state:
                st.session_state[wk] = bool(chk.get(chave, False))
            chk[chave] = st.checkbox(doc_nome, key=wk)
        envio_raw = list(listas_cat["TIPO_ENVIO"])
        if st.session_state["tipo_envio_docs"]:
            envio_raw.append(st.session_state["tipo_envio_docs"])
        lista_envio = [""] + ordenar_alfabetico_ptbr(envio_raw)
        st.selectbox(
            "Tipo de Envio dos Documentos",
            lista_envio,
            key=preparar_widget_lista("tipo_envio_docs", lista_envio),
            on_change=cb_sync_campo,
            args=("tipo_envio_docs",),
        )
        st.text_input(
            "Data de Envio dos Docs",
            key=preparar_widget("data_envio_docs"),
            on_change=cb_sync_campo,
            args=("data_envio_docs",),
            placeholder="",
        )
    with ck3:
        st.caption("**COOBRIGADOS**")
        for doc_nome in DOCS_COOBRIGADOS:
            chave = f"coob_{doc_nome}"
            wk = f"_w_chk_{chave}"
            if wk not in st.session_state:
                st.session_state[wk] = bool(chk.get(chave, False))
            chk[chave] = st.checkbox(doc_nome, key=wk)
    st.session_state["checklist_docs"] = chk

    # Botão rápido de impressão do Checklist de Documentos (para entregar ao cliente no atendimento)
    if tem_permissao("gerar_pdf"):
        sincronizar_widgets_para_estado()
        d_chk_pdf = montar_dicionario_proposta()
        nome_arq_chk = re.sub(r"[^A-Za-z0-9_-]+", "_", d_chk_pdf["cliente_nome"] or "CLIENTE").strip("_")
        pdf_chk_bytes = gerar_pdf_bytes(d_chk_pdf, ["CHECKLIST DE DOCUMENTOS"])
        c_chk_btn, c_chk_info = st.columns([1.6, 2.4])
        c_chk_btn.download_button(
            label="🖨️ Baixar / Imprimir Checklist de Documentos (PDF)",
            data=pdf_chk_bytes,
            file_name=f"CHECKLIST_DOCUMENTOS_{nome_arq_chk}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        c_chk_info.caption(
            "💡 Dica: gera uma folha A4 em Preto e Branco pronta para imprimir e entregar ao cliente "
            "(funciona mesmo em branco ou já com os itens marcados acima)."
        )

    # MARGEM CRÉDITO PESSOAL E AVALISTAS SEPARADOS
    st.divider()
    col_margem, col_aval = st.columns(2)

    with col_margem:
        st.markdown("#### 💳 Margem Crédito Pessoal e Consórcio")
        wk_mods = "_w_credito_modalidades"
        if wk_mods not in st.session_state:
            st.session_state[wk_mods] = [
                m for m in (st.session_state.get("credito_modalidades") or [])
                if m in TIPOS_CREDITO_PESSOAL_PADRAO
            ]
        st.multiselect(
            "Modalidade (marca com X no PDF — deixe vazio para marcar à mão na impressão)",
            options=ordenar_alfabetico_ptbr(TIPOS_CREDITO_PESSOAL_PADRAO),
            key=wk_mods,
            on_change=cb_sync_campo,
            args=("credito_modalidades",),
            placeholder="Selecione se desejar marcar automaticamente no PDF",
        )
        st.text_input(
            "Valor (R$)",
            key=preparar_widget_moeda("credito_valor"),
            on_change=cb_sync_campo,
            args=("credito_valor", False, True),
            placeholder="Ex.: 1.200,00",
        )
        st.caption("**Consórcio:**")
        m3, m4 = st.columns(2)
        m3.text_input(
            "Valor da Parcela do Consórcio (R$)",
            key=preparar_widget_moeda("parcela_consorcio"),
            on_change=cb_sync_campo,
            args=("parcela_consorcio", False, True),
            placeholder="Ex.: 850,00",
        )
        m4.number_input(
            "Quantidade de Parcelas do Consórcio",
            min_value=0,
            step=1,
            key=preparar_widget("num_parcelas_consorcio"),
            on_change=cb_sync_campo,
            args=("num_parcelas_consorcio",),
            placeholder="",
        )

    with col_aval:
        st.markdown("#### 🤝 Avalistas (Avalista e Cônjuge)")
        st.text_input("Nome Completo do Avalista", key=preparar_widget("avalista_nome"), on_change=cb_sync_campo, args=("avalista_nome",))
        st.text_input(
            "CPF/CNPJ do Avalista",
            key=preparar_widget("avalista_cpf"),
            on_change=cb_sync_campo,
            args=("avalista_cpf", True),
        )
        st.text_input("Nome Completo do Cônjuge do Avalista", key=preparar_widget("conjuge_avalista_nome"), on_change=cb_sync_campo, args=("conjuge_avalista_nome",))
        st.text_input(
            "CPF do Cônjuge do Avalista",
            key=preparar_widget("conjuge_avalista_cpf"),
            on_change=cb_sync_campo,
            args=("conjuge_avalista_cpf", True),
        )

    # PARECER DA AGÊNCIA BANCÁRIA
    st.divider()
    st.markdown("#### 🏦 Parecer da Agência Bancária")
    st.text_area(
        "Observações / Parecer da Agência (opcional — deixe em branco para preencher à mão no documento impresso):",
        key=preparar_widget("parecer_agencia"),
        on_change=cb_sync_campo,
        args=("parecer_agencia",),
        height=75,
    )


# ----------------------------------------------------------------------------
# ABA 2: ANÁLISE PRODUTIVA (COM R$ 0,00 E LINHA INTEIRA PARA NOME DA PROPRIEDADE)
# ----------------------------------------------------------------------------
elif aba_ativa == "🌱 2. Análise Produtiva":
    st.subheader("🌱 Análise Produtiva e Propriedades do Produtor")
    st.caption("A primeira propriedade representa o Imóvel Beneficiado. Os valores de venda e rendas extras são somados automaticamente ao final.")

    props = st.session_state["propriedades_lista"]
    col_add, col_rem = st.columns([1, 1])
    if col_add.button("➕ Adicionar Outra Propriedade"):
        sincronizar_widgets_para_estado()
        props.append(_propriedade_vazia())
        st.rerun()
    if len(props) > 1 and col_rem.button("➖ Remover Última Propriedade"):
        sincronizar_widgets_para_estado()
        props.pop()
        limpar_chaves_widgets()
        st.rerun()

    for idx, p in enumerate(props):
        titulo_box = "🏡 Propriedade 1 (Beneficiada)" if idx == 0 else f"🏡 Propriedade {idx + 1}"
        nome_exib = f" — {p.get('nome')}" if p.get("nome") else ""
        with st.expander(f"{titulo_box}{nome_exib}", expanded=(idx == 0)):
            def _pw(pref, campo_p, default_val=""):
                wk = f"_w_p_{pref}_{idx}"
                if wk not in st.session_state:
                    st.session_state[wk] = p.get(campo_p, default_val)
                return wk

            # Linha inteira dedicada ao Nome da Propriedade
            p["nome"] = st.text_input("Nome da Propriedade", key=_pw("nome", "nome", ""))
            r1c1, r1c2, r1c3 = st.columns(3)
            p["matricula"] = r1c1.text_input("Matrícula", key=_pw("mat", "matricula", ""))
            if f"_w_p_pes_{idx}" not in st.session_state:
                st.session_state[f"_w_p_pes_{idx}"] = num_int_ou_none(p.get("num_pes"))
            p["num_pes"] = r1c2.number_input("Nº Pés de Café", min_value=0, step=100, key=f"_w_p_pes_{idx}", placeholder="")
            p["espacamento"] = r1c3.text_input("Espaçamento", key=_pw("esp", "espacamento", ""))

            r2c1, r2c2, r2c3 = st.columns(3)
            p["variedades"] = r2c1.text_input("Variedades", key=_pw("var", "variedades", ""))
            p["idade"] = r2c2.text_input("Idade da Lavoura", key=_pw("id", "idade", ""))
            p["prev_2027"] = r2c3.text_input("Previsão Safra 2027", key=_pw("pr27", "prev_2027", ""))

            r3c1, r3c2, r3c3 = st.columns(3)
            p["prod_2026"] = r3c1.text_input("Produção 2026", key=_pw("p26", "prod_2026", ""))
            p["prod_2025"] = r3c2.text_input("Produção 2025", key=_pw("p25", "prod_2025", ""))
            p["prod_2024"] = r3c3.text_input("Produção 2024", key=_pw("p24", "prod_2024", ""))

            r4c1, r4c2, r4c3 = st.columns(3)
            for pref_v, campo_v in [("v26", "venda_2026"), ("v25", "venda_2025"), ("v24", "venda_2024")]:
                wk_v = f"_w_p_{pref_v}_{idx}"
                if wk_v not in st.session_state:
                    st.session_state[wk_v] = fmt_input_moeda_br(p.get(campo_v))
            r4c1.text_input(
                "Valor de Venda 2026 (R$)",
                key=f"_w_p_v26_{idx}",
                on_change=cb_sync_prop_moeda,
                args=(idx, "v26", "venda_2026"),
                placeholder="Ex.: 10.000,00",
            )
            r4c2.text_input(
                "Valor de Venda 2025 (R$)",
                key=f"_w_p_v25_{idx}",
                on_change=cb_sync_prop_moeda,
                args=(idx, "v25", "venda_2025"),
                placeholder="Ex.: 10.000,00",
            )
            r4c3.text_input(
                "Valor de Venda 2024 (R$)",
                key=f"_w_p_v24_{idx}",
                on_change=cb_sync_prop_moeda,
                args=(idx, "v24", "venda_2024"),
                placeholder="Ex.: 10.000,00",
            )
            p["venda_2026"] = parse_moeda_br(st.session_state.get(f"_w_p_v26_{idx}"))
            p["venda_2025"] = parse_moeda_br(st.session_state.get(f"_w_p_v25_{idx}"))
            p["venda_2024"] = parse_moeda_br(st.session_state.get(f"_w_p_v24_{idx}"))

    st.divider()
    st.markdown("#### 🐄 Semoventes, Renda Extra e Bens")
    sem = st.session_state["semoventes"]
    for campo_si in ("vacas_leite", "boi_corte", "novilhas", "bezerros"):
        if f"_w_sem_{campo_si}" not in st.session_state:
            st.session_state[f"_w_sem_{campo_si}"] = num_int_ou_none(sem.get(campo_si))
    if "_w_sem_litros_dia" not in st.session_state:
        st.session_state["_w_sem_litros_dia"] = num_float_ou_none(sem.get("litros_dia"))
    if "_w_sem_preco_litro" not in st.session_state:
        st.session_state["_w_sem_preco_litro"] = fmt_input_moeda_br(sem.get("preco_litro"))

    s1, s2, s3 = st.columns(3)
    sem["vacas_leite"] = s1.number_input("Vacas de Leite (qtd)", min_value=0, step=1, key="_w_sem_vacas_leite", placeholder="")
    sem["litros_dia"] = s2.number_input("Litros por Dia", min_value=0.0, step=5.0, key="_w_sem_litros_dia", placeholder="")
    s3.text_input(
        "Preço por Litro (R$)",
        key="_w_sem_preco_litro",
        on_change=cb_sync_sem_moeda,
        args=("preco_litro",),
        placeholder="Ex.: 2,45",
    )
    sem["preco_litro"] = parse_moeda_br(st.session_state.get("_w_sem_preco_litro"))

    s4, s5, s6 = st.columns(3)
    sem["boi_corte"] = s4.number_input("Boi de Corte (qtd)", min_value=0, step=1, key="_w_sem_boi_corte", placeholder="")
    sem["novilhas"] = s5.number_input("Novilhas (qtd)", min_value=0, step=1, key="_w_sem_novilhas", placeholder="")
    sem["bezerros"] = s6.number_input("Bezerros (qtd)", min_value=0, step=1, key="_w_sem_bezerros", placeholder="")

    re1, re2, re3, re4 = st.columns([2, 1, 2, 1])
    re1.text_input("Renda Extra 1 (Descrição)", key=preparar_widget("renda_extra_1_desc"), on_change=cb_sync_campo, args=("renda_extra_1_desc",))
    re2.text_input(
        "Valor Renda 1 (R$)",
        key=preparar_widget_moeda("renda_extra_1_val"),
        on_change=cb_sync_campo,
        args=("renda_extra_1_val", False, True),
        placeholder="Ex.: 10.000,00",
    )
    re3.text_input("Renda Extra 2 (Descrição)", key=preparar_widget("renda_extra_2_desc"), on_change=cb_sync_campo, args=("renda_extra_2_desc",))
    re4.text_input(
        "Valor Renda 2 (R$)",
        key=preparar_widget_moeda("renda_extra_2_val"),
        on_change=cb_sync_campo,
        args=("renda_extra_2_val", False, True),
        placeholder="Ex.: 10.000,00",
    )

    st.text_area("Relação de Bens (máquinas, veículos, benfeitorias)", key=preparar_widget("bens"), on_change=cb_sync_campo, args=("bens",), height=80)

    resumo_prod = montar_dicionario_proposta()
    with st.container(border=True):
        st.markdown("#### 💵 Resumo da Renda Bruta Anual (Sai somado na impressão quando preenchido)")
        rp1, rp2, rp3 = st.columns(3)
        rp1.markdown(f"**Soma Vendas 2026 (Propriedades):**\n\n### {fmt_moeda(resumo_prod['soma_vendas_2026']) or '&nbsp;'}")
        rp2.markdown(f"**Soma Rendas Extras:**\n\n### {fmt_moeda(resumo_prod['soma_rendas_extras']) or '&nbsp;'}")
        rp3.markdown(f"**RENDA BRUTA ANUAL TOTAL:**\n\n### {fmt_moeda(resumo_prod['renda_bruta_anual']) or '&nbsp;'}")


# ----------------------------------------------------------------------------
# ABA 3: ORDEM DE SERVIÇO & LGPD
# ----------------------------------------------------------------------------
elif aba_ativa == "🧾 3. Ordem de Serviço & LGPD":
    st.subheader("🧾 Ordem de Serviço")
    st.caption(
        "Configure abaixo a faixa de honorários, eventuais descontos ou acréscimos e a forma de pagamento. "
        "Na impressão, o cliente verá apenas o Subtotal, a porcentagem de Desconto concedida e o Total a Pagar."
    )

    st.text_area(
        "Descrição do Serviço (preenchida automaticamente pela Linha + Serviço escolhidos na Aba 1):",
        key=preparar_widget("descricao_servico"),
        on_change=cb_sync_campo,
        args=("descricao_servico",),
        height=95,
    )

    liberado_desconto = pode_dar_desconto_os()
    if not liberado_desconto:
        definir_campo("faixa_honorario_idx", 2)
        definir_campo("desconto_extra", None)

    os1, os2, os3 = st.columns([2.2, 1.1, 1.1])
    opcoes_faixa_chaves = sorted(
        list(FAIXAS_HONORARIOS.keys()),
        key=lambda k: chave_alfabetica_ptbr(FAIXAS_HONORARIOS[k]["rotulo"]),
    )
    os1.selectbox(
        "Faixa de Honorários (Define a porcentagem de desconto)",
        options=opcoes_faixa_chaves,
        format_func=lambda k: FAIXAS_HONORARIOS[k]["rotulo"],
        key=preparar_widget_lista("faixa_honorario_idx", opcoes_faixa_chaves),
        on_change=cb_sync_campo,
        args=("faixa_honorario_idx",),
        disabled=not liberado_desconto,
    )
    os2.text_input(
        "Desconto Extra Manual (R$)",
        key=preparar_widget_moeda("desconto_extra"),
        on_change=cb_sync_campo,
        args=("desconto_extra", False, True),
        placeholder="Ex.: 500,00",
        disabled=not liberado_desconto,
    )
    os3.text_input(
        "Acréscimos (R$)",
        key=preparar_widget_moeda("acrescimos"),
        on_change=cb_sync_campo,
        args=("acrescimos", False, True),
        placeholder="Ex.: 500,00",
    )

    if not tem_permissao("aplicar_desconto_os"):
        if st.session_state.get("desconto_liberado_por_admin"):
            st.success("🔓 Desconto na Ordem de Serviço liberado pelo Administrador para esta proposta.")
        else:
            with st.expander("🔑 Precisa conceder desconto? Liberação pontual com senha do Administrador"):
                with st.form("form_liberar_desconto_admin", clear_on_submit=True):
                    senha_adm_desc = st.text_input("Senha do Administrador", type="password")
                    if st.form_submit_button("🔓 Liberar Desconto nesta Proposta"):
                        if validar_senha_admin(senha_adm_desc):
                            st.session_state["desconto_liberado_por_admin"] = True
                            st.success("✅ Desconto liberado pelo Administrador!")
                            st.rerun()
                        else:
                            st.error("❌ Senha do Administrador inválida.")

    st.text_input("Forma de Pagamento", key=preparar_widget("forma_pagamento"), on_change=cb_sync_campo, args=("forma_pagamento",))

    # Painel financeiro espaçoso e bem organizado
    d_calc = montar_dicionario_proposta()
    val_prop_c = float(d_calc["valor_proposto"] or 0.0)
    desc_tot_c = float(d_calc["desconto"] or 0.0)
    if val_prop_c > 0 and desc_tot_c > 0:
        pct_desc_vis = (desc_tot_c / val_prop_c) * 100.0 if d_calc["desconto_extra"] else (d_calc["percentual_desconto_faixa"] * 100.0)
        txt_pct_desc_vis = fmt_pct_br(pct_desc_vis)
    else:
        txt_pct_desc_vis = "Sem desconto"

    if d_calc["valor_proposto"] and d_calc["percentual_honorario"] == 0 and not d_calc["valor_total_os"]:
        tot_txt = "ISENTO"
    else:
        tot_txt = fmt_moeda(d_calc["valor_total_os"]) or "—"

    with st.container(border=True):
        st.markdown("#### 💰 Resumo Financeiro da Ordem de Serviço")
        r1a, r1b = st.columns(2)
        r1a.markdown(f"**Valor Proposto da Operação:**\n\n### {fmt_moeda(d_calc['valor_proposto']) or '—'}")
        r1b.markdown(f"**Subtotal (Honorários 2,00%):**\n\n### {fmt_moeda(d_calc['valor_cheio_os']) or '—'}")

        st.divider()
        r2a, r2b, r2c = st.columns(3)
        r2a.markdown(f"**Porcentagem de Desconto (sai na OS):**\n\n#### {txt_pct_desc_vis}")
        r2b.markdown(f"**Desconto em Reais (controle interno):**\n\n#### {('- ' + fmt_moeda(d_calc['desconto'])) if d_calc['desconto'] else '—'}")
        r2c.markdown(f"**Acréscimos:**\n\n#### {fmt_moeda(d_calc['acrescimos']) or '—'}")

        st.divider()
        st.success(f"### ✅ TOTAL A PAGAR NA ORDEM DE SERVIÇO:  {tot_txt}")

    st.divider()
    st.subheader("🔒 Conferência do Termo LGPD (Proteção de Dados)")
    cnpj_cont_txt = fmt_doc(d_calc["contabilidade_cnpj"])
    cont_linha = f"{d_calc['contabilidade_nome']} (CNPJ: {cnpj_cont_txt})" if (d_calc["contabilidade_nome"] and cnpj_cont_txt) else d_calc["contabilidade_nome"]

    st.info(
        f"**Titular:** {d_calc['cliente_nome']}  |  **CPF/CNPJ:** {fmt_doc(d_calc['cliente_cpf'])}\n\n"
        f"**Contabilidade:** {cont_linha}\n\n"
        "Este documento é válido para todas as instituições financeiras e cooperativas de crédito."
    )

    if tem_permissao("criar_editar_proposta"):
        if st.button("💾 Salvar Proposta e Atualizar Cadastro no Banco", type="primary", use_container_width=True):
            pid = salvar_tudo_no_banco(silencioso=False)
            if pid:
                st.success(f"✅ Proposta #{pid} salva com sucesso no PostgreSQL! Agora você pode gerar os PDFs na Aba 4.")
    else:
        st.warning("🔒 Seu perfil é Somente Consulta. Peça ao Administrador para liberar permissão de criação/edição.")


# ----------------------------------------------------------------------------
# ABA 4: IMPRESSÃO / PDFs (P&B, MARGENS CONFORTÁVEIS, 1 FOLHA A4, MARCA D'ÁGUA)
# ----------------------------------------------------------------------------
elif aba_ativa == "🖨️ 4. Imprimir / PDFs (P&B)":
    st.subheader("🖨️ Impressão de Pacotes Bancários e Documentos Avulsos")
    if not tem_permissao("gerar_pdf"):
        st.warning("🔒 Seu usuário não tem autorização para gerar/imprimir PDFs. Solicite liberação ao Administrador.")
    else:
        st.info(
            "🖨️ **Padrão de Impressão Ativado:** Preto e Branco • Margens confortáveis (1,4 cm × 1,3 cm) • "
            "Distribuição equilibrada em 1 folha A4 por documento • Marca d'água oficial da Regularize em todas as folhas."
        )

        d_pdf = montar_dicionario_proposta()
        nome_arquivo_base = re.sub(r"[^A-Za-z0-9_-]+", "_", d_pdf["cliente_nome"] or "PROPOSTA").strip("_")

        col_pac, col_ind = st.columns(2)

        with col_pac:
            st.markdown("### 📦 Pacote Completo por Instituição")
            opcoes_pacotes_ord = ordenar_alfabetico_ptbr(list(PACOTES_BANCOS.keys()))
            banco_pacote = st.selectbox("Escolha o Pacote Bancário:", opcoes_pacotes_ord)
            opcoes_docs_cli_ord = ordenar_alfabetico_ptbr(DOCUMENTOS_CLIENTE_PADRAO + ["GALPÃO DE GRÃOS", "CHECKLIST DE DOCUMENTOS"])
            incluir_abas_cliente = st.multiselect(
                "Quais documentos do cliente incluir no início do pacote?",
                options=opcoes_docs_cli_ord,
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
            doc_avulso = st.selectbox(f"Escolha qualquer um dos {len(TODOS_OS_DOCUMENTOS)} documentos:", ordenar_alfabetico_ptbr(TODOS_OS_DOCUMENTOS))
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
elif aba_ativa == "🗂️ 5. Histórico & Cadastros":
    st.subheader("🗂️ Histórico de Propostas Salvas")
    f1, f2, f3 = st.columns([2, 1.5, 1])
    busca_hist = f1.text_input("Filtrar por Nome ou CPF/CNPJ:", placeholder="")
    banco_hist = f2.selectbox("Filtrar por Banco:", ["TODOS"] + ordenar_alfabetico_ptbr(listas_cat["BANCO"]))
    limite_hist = f3.number_input("Máximo de registros", min_value=20, max_value=2000, value=200, step=50)

    ver_todos = tem_permissao("ver_historico_todos")
    if not ver_todos:
        st.caption("🔒 Exibindo apenas as propostas criadas pelo seu usuário. (Para ver a equipe toda, solicite autorização ao Administrador).")

    sql_hist = text("""
        SELECT p.id, p.data_proposta, c.nome AS cliente, p.cliente_cpf_cnpj AS cpf_cnpj,
               p.banco_destino AS banco, COALESCE(p.banco_municipio, '') AS banco_municipio, p.tipo_servico AS servico,
               p.item_financiado AS item, p.valor_proposto, p.valor_total_os,
               p.criado_por, p.criado_em
        FROM propostas p
        JOIN clientes c ON c.cpf_cnpj = p.cliente_cpf_cnpj
        WHERE (:busca = '' OR UPPER(c.nome) LIKE :termo OR p.cliente_cpf_cnpj LIKE :termo_num)
          AND (:banco = 'TODOS' OR p.banco_destino = :banco)
          AND (:ver_todos = TRUE OR LOWER(p.criado_por) = :usuario_atual)
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
                "ver_todos": ver_todos,
                "usuario_atual": usuario_atual,
                "lim": int(limite_hist),
            },
        )

    if not df_hist.empty:
        df_exibir = df_hist.copy()
        df_exibir["cpf_cnpj"] = df_exibir["cpf_cnpj"].apply(fmt_doc)
        df_exibir["data_proposta"] = pd.to_datetime(df_exibir["data_proposta"]).dt.strftime("%d/%m/%Y")
        df_exibir["valor_proposto_fmt"] = df_exibir["valor_proposto"].apply(lambda x: fmt_moeda(x))
        df_exibir["valor_total_os_fmt"] = df_exibir["valor_total_os"].apply(lambda x: fmt_moeda(x))
        df_exibir["criado_em"] = pd.to_datetime(df_exibir["criado_em"]).dt.strftime("%d/%m/%Y %H:%M")

        df_tabela = df_exibir[[
            "id", "data_proposta", "cliente", "cpf_cnpj", "banco", "banco_municipio",
            "servico", "item", "valor_proposto_fmt", "valor_total_os_fmt",
            "criado_por", "criado_em",
        ]].fillna("").rename(columns={
            "id": "Nº",
            "data_proposta": "Data",
            "cliente": "Produtor / Cliente",
            "cpf_cnpj": "CPF/CNPJ",
            "banco": "Banco",
            "banco_municipio": "Município Banco",
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
            f"{r['cliente']} | #{r['id']} | {pd.to_datetime(r['data_proposta']).strftime('%d/%m/%Y')} {('(' + r['banco'] + ')') if r['banco'] else ''} {fmt_moeda(r['valor_proposto'])}".strip(): int(r["id"])
            for _, r in df_hist.iterrows()
        }
        chaves_props_ord = ordenar_alfabetico_ptbr(list(op_props.keys()))
        prop_sel = c_load.selectbox("Abrir proposta do histórico para editar ou reimprimir:", chaves_props_ord)
        c_load.button(
            "📂 Carregar Proposta Selecionada",
            on_click=cb_carregar_proposta,
            args=(op_props[prop_sel],),
        )

        if tem_permissao("exportar_excel"):
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
            c_exp.caption("🔒 Exportação em Excel restrita ao Admin/Supervisor.")
    else:
        st.info("Nenhuma proposta salva encontrada para os filtros informados.")

    st.divider()
    st.subheader("🏢 Cadastrar Nova Contabilidade")
    if not tem_permissao("cadastrar_contabilidade"):
        st.caption("🔒 Seu usuário não tem autorização para cadastrar novas contabilidades.")
    else:
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
                            {"n": novo_nome_cont.strip(), "c": fmt_doc(novo_cnpj_cont.strip())},
                        )
                    carregar_listas_auxiliares.clear()
                    st.success(f"✅ Contabilidade '{novo_nome_cont.strip()}' cadastrada com sucesso!")
                    st.rerun()
                else:
                    st.warning("Informe o nome da contabilidade.")


# ----------------------------------------------------------------------------
# ABA 6: PAINEL DO ADMINISTRADOR (ÍCONES INTERATIVOS DE USUÁRIOS ATIVOS + SENHA)
# ----------------------------------------------------------------------------
elif aba_ativa == "🔐 6. Administração (Usuários)" and eh_admin_painel:
    st.subheader("🔐 Administração de Usuários e Autorizações")

    # ========================================================================
    # DESBLOQUEIO DO PAINEL POR SENHA DO ADMINISTRADOR
    # (Permite clicar direto nos ícones ✅ Ativo / ⛔ Desativado e gerenciar tudo!)
    # ========================================================================
    painel_liberado = bool(st.session_state.get("admin_painel_liberado", False))
    with st.container(border=True):
        if painel_liberado:
            c_st1, c_st2 = st.columns([3.5, 1.0])
            c_st1.success(
                "🔓 **Painel Administrativo Desbloqueado!** Agora você pode clicar diretamente nos ícones "
                "**✅ Ativo / ⛔ Desativado** para ligar ou bloquear qualquer usuário na hora, além de criar e editar autorizações."
            )
            c_st2.write("")
            if c_st2.button("🔒 Bloquear Painel", use_container_width=True):
                st.session_state["admin_painel_liberado"] = False
                st.rerun()
        else:
            st.info(
                "🛡️ **Proteção por Senha do Administrador:** Para ativar/desativar usuários clicando nos ícones, "
                "adicionar novos acessos ou alterar autorizações, informe a **Senha do Administrador** abaixo."
            )
            with st.form("form_desbloquear_painel_admin", clear_on_submit=True):
                cu1, cu2 = st.columns([3, 1.2])
                senha_unlock = cu1.text_input(
                    "🔑 Senha do Administrador",
                    type="password",
                    placeholder="Digite sua senha de Administrador e clique em Desbloquear",
                    label_visibility="collapsed",
                )
                if cu2.form_submit_button("🔓 Desbloquear Painel", type="primary", use_container_width=True):
                    if validar_senha_admin(senha_unlock):
                        st.session_state["admin_painel_liberado"] = True
                        st.toast("🔓 Painel Administrativo desbloqueado!")
                        st.rerun()
                    else:
                        st.error("❌ Senha do Administrador incorreta.")

    if st.session_state.get("_msg_admin_acao"):
        tipo_m, txt_m = st.session_state["_msg_admin_acao"]
        if tipo_m == "ok":
            st.success(txt_m)
        elif tipo_m == "warn":
            st.warning(txt_m)
        else:
            st.error(txt_m)
        st.session_state["_msg_admin_acao"] = None

    # Carregar usuários diretamente do PostgreSQL
    with engine.connect() as conn:
        df_users = pd.read_sql(
            text("""
                SELECT email, nome, perfil, ativo, permissoes, criado_por, criado_em, atualizado_em, ultimo_acesso
                FROM usuarios_sistema
                ORDER BY LOWER(email)
            """),
            conn,
        )

    # Métricas rápidas no topo
    agora_utc = datetime.now(timezone.utc)
    total_u = len(df_users)
    ativos_u = 0
    inativos_u = 0
    online_u = 0
    registros_u = []

    for _, ru in df_users.iterrows():
        email_u = str(ru["email"]).strip().lower()
        eh_m = eh_admin_master(email_u)
        esta_ativo = True if eh_m else bool(ru["ativo"])
        if esta_ativo:
            ativos_u += 1
        else:
            inativos_u += 1

        ult_acesso = ru.get("ultimo_acesso")
        esta_online = False
        ult_txt = "Ainda não acessou"
        if pd.notna(ult_acesso):
            dt_u = pd.to_datetime(ult_acesso)
            if dt_u.tzinfo is None:
                dt_u = dt_u.tz_localize("UTC")
            diff_min = (agora_utc - dt_u.to_pydatetime()).total_seconds() / 60.0
            if diff_min <= 10:
                esta_online = True
                online_u += 1
            dt_br = dt_u.astimezone(FUSO_BRASILIA)
            ult_txt = dt_br.strftime("%d/%m/%Y %H:%M")

        p_dict = ru["permissoes"] if isinstance(ru["permissoes"], dict) else {}
        perms_ativas = [
            k.replace("_", " ").title()
            for k in PERMISSOES_DESCRICAO.keys()
            if (eh_m or ru["perfil"] == "ADMIN" or p_dict.get(k, False))
        ]
        registros_u.append({
            "email": email_u,
            "nome": ru["nome"] or email_u.split("@")[0].title(),
            "perfil": ru["perfil"],
            "eh_master": eh_m,
            "ativo": esta_ativo,
            "online": esta_online,
            "ultimo_acesso_txt": ult_txt,
            "perms_resumo": ", ".join(perms_ativas) if perms_ativas else "Nenhuma",
        })

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("👥 Total de Usuários", total_u)
    m2.metric("✅ Usuários Ativos", ativos_u)
    m3.metric("⛔ Desativados", inativos_u)
    m4.metric("🟢 Online Agora", online_u)

    # ========================================================================
    # LISTA INTERATIVA DE USUÁRIOS (ÍCONES ✅ ATIVO / ⛔ DESATIVADO CLICÁVEIS!)
    # ========================================================================
    st.markdown("#### 👥 Usuários Cadastrados — Clique no ícone de Status para Ativar ou Desativar")
    if not registros_u:
        st.info("Nenhum usuário cadastrado ainda.")
    else:
        with st.container(border=True):
            h1, h2, h3, h4, h5 = st.columns([1.25, 2.3, 1.35, 2.6, 0.95])
            h1.markdown("**Status (Clique)**")
            h2.markdown("**Usuário / Presença**")
            h3.markdown("**Perfil**")
            h4.markdown("**Autorizações Liberadas**")
            h5.markdown("**Ação**")
            st.divider()

            def _cb_selecionar_usuario_edicao(email_escolhido):
                st.session_state["adm_edit_sel"] = email_escolhido

            for idx_u, r in enumerate(registros_u):
                c_st, c_usr, c_prf, c_prm, c_ed = st.columns([1.25, 2.3, 1.35, 2.6, 0.95])

                # 1. Ícone/Botão clicável de Status (Ativo / Desativado)
                if r["eh_master"]:
                    c_st.button(
                        "👑 Ativo",
                        key=f"btn_status_u_{idx_u}_{r['email']}",
                        disabled=True,
                        help="Conta Admin Master sempre ativa e protegida.",
                        use_container_width=True,
                    )
                else:
                    label_st = "✅ Ativo" if r["ativo"] else "⛔ Desativado"
                    help_st = (
                        "Clique para DESATIVAR (bloquear login) deste usuário."
                        if r["ativo"]
                        else "Clique para ATIVAR (liberar login) deste usuário."
                    )
                    if c_st.button(
                        label_st,
                        key=f"btn_status_u_{idx_u}_{r['email']}",
                        help=help_st,
                        use_container_width=True,
                    ):
                        if not painel_liberado:
                            st.session_state["_msg_admin_acao"] = (
                                "warn",
                                "🔒 Digite a **Senha do Administrador** no topo da Aba 6 e clique em **🔓 Desbloquear Painel** para ativar ou desativar usuários pelos ícones.",
                            )
                            st.rerun()
                        else:
                            ok, msg_res = alternar_status_usuario_db(r["email"], not r["ativo"])
                            st.session_state["_msg_admin_acao"] = ("ok" if ok else "err", msg_res)
                            st.toast(msg_res)
                            st.rerun()

                # 2. Nome, e-mail e indicador online / último acesso
                badge_presenca = "🟢 **Online agora**" if r["online"] else f"⚪ Acesso: {r['ultimo_acesso_txt']}"
                c_usr.markdown(f"**{r['nome']}**  \n`{r['email']}`  \n{badge_presenca}")

                # 3. Perfil
                rot_p = "👑 ADMIN MASTER" if r["eh_master"] else f"🛡️ {r['perfil']}"
                c_prf.markdown(f"**{rot_p}**")

                # 4. Autorizações resumidas
                c_prm.caption(r["perms_resumo"])

                # 5. Botão rápido para abrir no editor abaixo
                c_ed.button(
                    "⚙️ Editar",
                    key=f"btn_editar_u_{idx_u}_{r['email']}",
                    on_click=_cb_selecionar_usuario_edicao,
                    args=(r["email"],),
                    use_container_width=True,
                )

                if idx_u < len(registros_u) - 1:
                    st.markdown("<hr style='margin:6px 0; border:none; border-top:1px solid #E2E8F0;'>", unsafe_allow_html=True)

    st.divider()
    col_add_u, col_edit_u = st.columns(2)

    # ========================================================================
    # BLOCO A: ADICIONAR NOVO USUÁRIO (SOMENTE ADMIN COM SENHA)
    # ========================================================================
    with col_add_u:
        st.markdown("### ➕ Adicionar Novo Usuário")
        perfis_ord_chaves = ordenar_alfabetico_ptbr(list(PERFIS_AUTORIZACAO.keys()))
        perfil_novo = st.selectbox(
            "Perfil de Autorização do Novo Usuário",
            options=perfis_ord_chaves,
            format_func=lambda k: f"{k} — {PERFIS_AUTORIZACAO[k]['rotulo']}",
            index=perfis_ord_chaves.index("ATENDENTE"),
            key="adm_novo_perfil",
        )
        perms_modelo_novo = dict(PERFIS_AUTORIZACAO[perfil_novo]["permissoes"])

        with st.form("form_adm_add_usuario", clear_on_submit=True):
            novo_nome_u = st.text_input("Nome completo do usuário *")
            novo_email_u = st.text_input("E-mail de acesso *").strip().lower()
            nova_senha_u = st.text_input("Senha inicial do usuário *", type="password")
            nova_senha_u2 = st.text_input("Confirmar senha inicial *", type="password")

            st.markdown("**Autorizações que serão liberadas para este usuário:**")
            perms_escolhidas_novo = {}
            for chave_p, desc_p in PERMISSOES_DESCRICAO.items():
                val_def = bool(perms_modelo_novo.get(chave_p, False))
                if perfil_novo == "ADMIN":
                    st.checkbox(desc_p, value=True, disabled=True, key=f"adm_new_p_{perfil_novo}_{chave_p}")
                    perms_escolhidas_novo[chave_p] = True
                else:
                    perms_escolhidas_novo[chave_p] = st.checkbox(
                        desc_p,
                        value=val_def,
                        key=f"adm_new_p_{perfil_novo}_{chave_p}",
                    )

            st.divider()
            if painel_liberado:
                senha_admin_add = ""
                st.caption("🔓 Painel já desbloqueado pela Senha do Administrador nesta sessão.")
            else:
                senha_admin_add = st.text_input(
                    "🔑 Senha do Administrador (obrigatória para liberar cadastro) *",
                    type="password",
                )
            btn_criar_u = st.form_submit_button("✅ Criar Usuário e Liberar Autorizações", type="primary", use_container_width=True)

            if btn_criar_u:
                autorizado_add = painel_liberado or validar_senha_admin(senha_admin_add)
                if not autorizado_add:
                    st.error("❌ Senha do Administrador incorreta! Operação bloqueada.")
                elif not novo_nome_u.strip() or not novo_email_u or "@" not in novo_email_u:
                    st.error("❌ Informe um Nome e um E-mail válido.")
                elif len(nova_senha_u) < 4:
                    st.error("❌ A senha inicial do usuário deve ter pelo menos 4 caracteres.")
                elif nova_senha_u != nova_senha_u2:
                    st.error("❌ A confirmação da senha inicial não confere.")
                else:
                    st.session_state["admin_painel_liberado"] = True
                    if perfil_novo == "ADMIN":
                        perms_finais = {k: True for k in PERMISSOES_DESCRICAO}
                    else:
                        perms_finais = perms_escolhidas_novo
                    with engine.begin() as conn:
                        ja_existe = conn.execute(
                            text("SELECT 1 FROM usuarios_sistema WHERE LOWER(email) = :e"),
                            {"e": novo_email_u},
                        ).first()
                        if ja_existe:
                            st.error(f"❌ Já existe um usuário cadastrado com o e-mail '{novo_email_u}'. Use o painel ao lado para editá-lo.")
                        else:
                            conn.execute(
                                text("""
                                    INSERT INTO usuarios_sistema (
                                        email, nome, senha_hash, perfil, ativo, permissoes, criado_por
                                    ) VALUES (
                                        :e, :n, :sh, :perf, TRUE, CAST(:perms AS jsonb), :cp
                                    )
                                """),
                                {
                                    "e": novo_email_u,
                                    "n": novo_nome_u.strip(),
                                    "sh": gerar_hash_senha(nova_senha_u),
                                    "perf": perfil_novo,
                                    "perms": json.dumps(perms_finais, ensure_ascii=False),
                                    "cp": usuario_atual,
                                },
                            )
                            st.session_state["_msg_admin_acao"] = ("ok", f"✅ Usuário '{novo_nome_u.strip()}' ({novo_email_u}) criado com sucesso!")
                            st.rerun()

    # ========================================================================
    # BLOCO B: LIBERAR/EDITAR AUTORIZAÇÕES, SENHA OU STATUS DE USUÁRIO
    # ========================================================================
    with col_edit_u:
        st.markdown("### 🛡️ Gerenciar Autorizações e Senha de Usuário")
        if df_users.empty:
            st.caption("Cadastre o primeiro usuário ao lado.")
        else:
            lista_emails_u = ordenar_alfabetico_ptbr(df_users["email"].tolist())
            if st.session_state.get("adm_edit_sel") not in lista_emails_u:
                st.session_state["adm_edit_sel"] = lista_emails_u[0]
            email_sel = st.selectbox("Selecione o usuário para configurar:", lista_emails_u, key="adm_edit_sel")
            u_edit = carregar_usuario_db(email_sel)

            if u_edit:
                eh_sel_master = u_edit["eh_master"]
                if eh_sel_master:
                    st.info("👑 **Conta ADMIN MASTER:** protegida contra desativação, exclusão ou remoção de permissões. Você pode alterar o nome ou redefinir a senha abaixo.")

                op_perfis = ordenar_alfabetico_ptbr(list(PERFIS_AUTORIZACAO.keys()))
                idx_p_u = op_perfis.index(u_edit["perfil"]) if u_edit["perfil"] in op_perfis else op_perfis.index("PERSONALIZADO")
                perfil_edit = st.selectbox(
                    "Alterar Perfil Base (atualiza as sugestões abaixo):",
                    options=op_perfis,
                    index=idx_p_u,
                    format_func=lambda k: f"{k} — {PERFIS_AUTORIZACAO[k]['rotulo']}",
                    key=f"adm_edit_perf_{email_sel}",
                    disabled=eh_sel_master,
                )
                usar_modelo_perfil = (not eh_sel_master) and (perfil_edit != u_edit["perfil"])
                perms_base_edit = (
                    dict(PERFIS_AUTORIZACAO[perfil_edit]["permissoes"])
                    if usar_modelo_perfil
                    else dict(u_edit["permissoes"])
                )

                with st.form(f"form_adm_edit_u_{email_sel}_{u_edit['ativo']}"):
                    edit_nome = st.text_input("Nome do usuário", value=u_edit["nome"], key=f"adm_ed_nome_{email_sel}")
                    edit_ativo = st.checkbox(
                        "Usuário ATIVO (desmarque para bloquear o login)",
                        value=True if eh_sel_master else u_edit["ativo"],
                        disabled=eh_sel_master,
                        key=f"adm_ed_ativo_{email_sel}_{u_edit['ativo']}",
                    )
                    edit_nova_senha = st.text_input(
                        "Redefinir senha deste usuário (deixe em branco para manter a senha atual)",
                        type="password",
                    )

                    st.markdown("**Tipos de Autorizações Liberadas:**")
                    perms_edit_marcadas = {}
                    for chave_p, desc_p in PERMISSOES_DESCRICAO.items():
                        trava_admin = eh_sel_master or (perfil_edit == "ADMIN")
                        val_atual = True if trava_admin else bool(perms_base_edit.get(chave_p, False))
                        if trava_admin:
                            st.checkbox(desc_p, value=True, disabled=True, key=f"adm_ed_{email_sel}_{perfil_edit}_{chave_p}")
                            perms_edit_marcadas[chave_p] = True
                        else:
                            perms_edit_marcadas[chave_p] = st.checkbox(
                                desc_p,
                                value=val_atual,
                                key=f"adm_ed_{email_sel}_{perfil_edit}_{chave_p}",
                            )

                    st.divider()
                    if painel_liberado:
                        senha_admin_edit = ""
                        st.caption("🔓 Painel já desbloqueado pela Senha do Administrador nesta sessão.")
                    else:
                        senha_admin_edit = st.text_input(
                            "🔑 Senha do Administrador (obrigatória para salvar alterações) *",
                            type="password",
                        )
                    btn_salvar_u = st.form_submit_button("💾 Salvar Alterações e Autorizações", type="primary", use_container_width=True)

                    if btn_salvar_u:
                        autorizado_edit = painel_liberado or validar_senha_admin(senha_admin_edit)
                        if not autorizado_edit:
                            st.error("❌ Senha do Administrador incorreta! Nenhuma alteração foi salva.")
                        elif email_sel == usuario_atual and (not edit_ativo or not perms_edit_marcadas.get("gerenciar_usuarios")):
                            st.error("❌ Você não pode desativar ou remover o acesso de Administrador do seu próprio usuário logado.")
                        elif edit_nova_senha and len(edit_nova_senha) < 4:
                            st.error("❌ A nova senha deve ter pelo menos 4 caracteres.")
                        else:
                            st.session_state["admin_painel_liberado"] = True
                            if eh_sel_master:
                                perfil_gravar = "ADMIN"
                                ativo_gravar = True
                                perms_gravar = {k: True for k in PERMISSOES_DESCRICAO}
                            else:
                                perfil_gravar = perfil_edit
                                ativo_gravar = bool(edit_ativo)
                                perms_gravar = perms_edit_marcadas
                                if perfil_edit != "ADMIN" and perms_edit_marcadas != PERFIS_AUTORIZACAO[perfil_edit]["permissoes"]:
                                    perfil_gravar = "PERSONALIZADO"

                            with engine.begin() as conn:
                                if edit_nova_senha:
                                    conn.execute(
                                        text("""
                                            UPDATE usuarios_sistema SET
                                                nome = :n,
                                                senha_hash = :sh,
                                                perfil = :perf,
                                                ativo = :at,
                                                permissoes = CAST(:perms AS jsonb),
                                                atualizado_em = NOW()
                                            WHERE LOWER(email) = :e
                                        """),
                                        {
                                            "n": edit_nome.strip(),
                                            "sh": gerar_hash_senha(edit_nova_senha),
                                            "perf": perfil_gravar,
                                            "at": ativo_gravar,
                                            "perms": json.dumps(perms_gravar, ensure_ascii=False),
                                            "e": email_sel.lower(),
                                        },
                                    )
                                else:
                                    conn.execute(
                                        text("""
                                            UPDATE usuarios_sistema SET
                                                nome = :n,
                                                perfil = :perf,
                                                ativo = :at,
                                                permissoes = CAST(:perms AS jsonb),
                                                atualizado_em = NOW()
                                            WHERE LOWER(email) = :e
                                        """),
                                        {
                                            "n": edit_nome.strip(),
                                            "perf": perfil_gravar,
                                            "at": ativo_gravar,
                                            "perms": json.dumps(perms_gravar, ensure_ascii=False),
                                            "e": email_sel.lower(),
                                        },
                                    )
                            limpar_cache_form_admin_usuario(email_sel)
                            st.session_state["_msg_admin_acao"] = ("ok", f"✅ Dados e autorizações de '{email_sel}' atualizados com sucesso!")
                            st.rerun()

                if (not eh_sel_master) and (email_sel != usuario_atual):
                    with st.expander(f"🗑️ Excluir permanentemente o usuário {email_sel}"):
                        with st.form(f"form_del_u_{email_sel}", clear_on_submit=True):
                            st.warning("Atenção: o histórico de propostas criadas por este usuário será mantido, mas o login dele será removido.")
                            senha_admin_del = st.text_input("🔑 Senha do Administrador para confirmar exclusão *", type="password")
                            if st.form_submit_button("🗑️ Confirmar Exclusão do Usuário"):
                                if validar_senha_admin(senha_admin_del):
                                    with engine.begin() as conn:
                                        conn.execute(
                                            text("DELETE FROM usuarios_sistema WHERE LOWER(email) = :e"),
                                            {"e": email_sel.lower()},
                                        )
                                    limpar_cache_form_admin_usuario(email_sel)
                                    st.session_state["_msg_admin_acao"] = ("ok", f"🗑️ Usuário '{email_sel}' excluído permanentemente.")
                                    st.rerun()
                                else:
                                    st.error("❌ Senha do Administrador incorreta.")
