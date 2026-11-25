# ============================================================================
# ARQUIVO: pdf_generator.py
# O QUE ESTE ARQUIVO FAZ:
#   Gera TODOS os 23 documentos oficiais em PDF seguindo o padrão visual da
#   planilha Excel da Regularize Assessoria Rural:
#   - 100% em Preto e Branco (otimizado para impressão nítida e econômica)
#   - Exatamente 1 página A4 por documento (sem quebrar folha)
#   - Marca d'água da Regularize em TODAS as folhas impressas
#   - CPF/CNPJ sempre formatados com pontos, traço e barra
#   - Ordem de Serviço mostrando Valor Cheio (2,00%) + Desconto da Faixa
#   - Carta-Proposta com Margem Crédito Pessoal separada de Avalistas,
#     espaço para Parecer da Agência e bloco de 4 Assinaturas padronizado.
# ============================================================================

import io
import os
from datetime import date, datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import (
    DOCS_COOBRIGADOS,
    DOCS_IMOVEL,
    DOCS_PROPONENTE,
    EMPRESA,
    TAXA_HONORARIO_CHEIA,
)

# Caminho dos arquivos de imagem P&B (na mesma pasta deste script)
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))


def _achar_arquivo(nome):
    """Procura a imagem na raiz do projeto ou na pasta assets/."""
    for caminho in [
        os.path.join(PASTA_ATUAL, nome),
        os.path.join(PASTA_ATUAL, "assets", nome),
        nome,
    ]:
        if os.path.exists(caminho):
            return caminho
    return None


# ============================================================================
# FUNÇÕES DE FORMATAÇÃO NO PADRÃO BRASILEIRO (PT-BR)
# ============================================================================
def fmt_moeda(valor):
    """Formata 500000 como 'R$ 500.000,00'."""
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0.0
    sinal = "-" if v < 0 else ""
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {texto}"


def fmt_doc(cpf_cnpj):
    """Formata CPF (000.000.000-00) ou CNPJ (00.000.000/0000-00)."""
    d = "".join(ch for ch in str(cpf_cnpj or "") if ch.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return str(cpf_cnpj or "")


def fmt_cep(cep):
    """Formata CEP como 00000-000."""
    d = "".join(ch for ch in str(cep or "") if ch.isdigit())
    if len(d) == 8:
        return f"{d[:5]}-{d[5:]}"
    return str(cep or "")


def fmt_data_extenso(dt=None):
    """Formata data por extenso em PT-BR: '25 de novembro de 2026'."""
    if not dt:
        dt = date.today()
    elif isinstance(dt, str):
        try:
            dt = datetime.strptime(dt[:10], "%Y-%m-%d").date()
        except ValueError:
            return dt
    meses = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    return f"{dt.day:02d} de {meses[dt.month - 1]} de {dt.year}"


def fmt_data_br(dt=None):
    """Formata data como '25/11/2026'."""
    if not dt:
        dt = date.today()
    elif isinstance(dt, str):
        try:
            dt = datetime.strptime(dt[:10], "%Y-%m-%d").date()
        except ValueError:
            return dt
    return dt.strftime("%d/%m/%Y")


def safe(texto):
    """Protege caracteres especiais para o motor PDF."""
    return escape(str(texto or ""))


# ============================================================================
# MARCA D'ÁGUA DA REGULARIZE (APLICADA AUTOMATICAMENTE EM TODAS AS FOLHAS)
# ============================================================================
def desenhar_marca_dagua_e_rodape(canvas, doc):
    """
    Função chamada automaticamente pelo ReportLab em TODA folha impressa.
    Desenha a marca d'água da Regularize centralizada atrás do conteúdo em P&B.
    """
    canvas.saveState()
    largura_pag, altura_pag = A4

    wm_path = _achar_arquivo("marca_dagua_regularize.png")
    if wm_path:
        # Centraliza a marca d'água oficial da planilha em tamanho proporcional
        wm_w = 13.5 * cm
        wm_h = 10.75 * cm
        x = (largura_pag - wm_w) / 2.0
        y = (altura_pag - wm_h) / 2.0
        canvas.drawImage(
            wm_path, x, y, width=wm_w, height=wm_h,
            mask="auto", preserveAspectRatio=True, anchor="c",
        )
    else:
        # Caso a imagem PNG não esteja na pasta, desenha marca d'água em texto P&B
        canvas.translate(largura_pag / 2.0, altura_pag / 2.0)
        canvas.rotate(38)
        canvas.setFillColor(colors.HexColor("#E2E2E2"))
        canvas.setFont("Helvetica-Bold", 38)
        canvas.drawCentredString(0, 12, "REGULARIZE")
        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawCentredString(0, -14, "ASSESSORIA RURAL LTDA")

    canvas.restoreState()


# ============================================================================
# ESTILOS 100% PRETO E BRANCO (OTIMIZADO PARA 1 PÁGINA POR FOLHA)
# ============================================================================
def criar_estilos_pb():
    base = getSampleStyleSheet()
    cor_preto = colors.black
    cor_borda = colors.HexColor("#333333")
    cor_faixa = colors.HexColor("#E8E8E8")  # Cinza bem claro para cabeçalhos em P&B

    return {
        "cor_preto": cor_preto,
        "cor_borda": cor_borda,
        "cor_faixa": cor_faixa,
        "titulo": ParagraphStyle(
            "TituloPB", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=12, leading=14, alignment=TA_CENTER, textColor=cor_preto,
            spaceAfter=2,
        ),
        "subtitulo_doc": ParagraphStyle(
            "SubtituloDocPB", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=10.5, alignment=TA_CENTER, textColor=cor_preto,
            spaceAfter=3,
        ),
        "secao": ParagraphStyle(
            "SecaoPB", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=10.5, alignment=TA_CENTER, textColor=cor_preto,
        ),
        "normal": ParagraphStyle(
            "NormalPB", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.2, leading=10.5, alignment=TA_LEFT, textColor=cor_preto,
        ),
        "normal_bold": ParagraphStyle(
            "NormalBoldPB", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.2, leading=10.5, alignment=TA_LEFT, textColor=cor_preto,
        ),
        "justificado": ParagraphStyle(
            "JustificadoPB", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.5, leading=12, alignment=TA_JUSTIFY, textColor=cor_preto,
            spaceAfter=5,
        ),
        "pequeno": ParagraphStyle(
            "PequenoPB", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.2, leading=9.3, alignment=TA_JUSTIFY, textColor=cor_preto,
            spaceAfter=2.5,
        ),
        "micro": ParagraphStyle(
            "MicroPB", parent=base["Normal"], fontName="Helvetica",
            fontSize=6.8, leading=8.5, alignment=TA_LEFT, textColor=cor_preto,
        ),
        "centro": ParagraphStyle(
            "CentroPB", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.2, leading=10.5, alignment=TA_CENTER, textColor=cor_preto,
        ),
        "centro_bold": ParagraphStyle(
            "CentroBoldPB", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.2, leading=10.5, alignment=TA_CENTER, textColor=cor_preto,
        ),
        "direita": ParagraphStyle(
            "DireitaPB", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.2, leading=10.5, alignment=TA_RIGHT, textColor=cor_preto,
        ),
        "direita_bold": ParagraphStyle(
            "DireitaBoldPB", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.2, leading=10.5, alignment=TA_RIGHT, textColor=cor_preto,
        ),
    }


def bloco_cabecalho_planilha(titulo, est, subtitulo_extra=""):
    """
    Cabeçalho fiel à planilha original em Preto e Branco:
    Logo Regularize P&B à esquerda + Título do documento em destaque à direita.
    """
    logo_path = _achar_arquivo("logo_regularize_pb.png")
    if logo_path:
        cel_logo = RLImage(logo_path, width=3.9 * cm, height=1.14 * cm)
    else:
        cel_logo = Paragraph(
            f"<b>{safe(EMPRESA['nome_fantasia'].upper())}</b><br/><font size=6.5>CNPJ: {safe(EMPRESA['cnpj'])}</font>",
            est["normal"],
        )

    txt_dir = f"<b>{safe(titulo)}</b>"
    if subtitulo_extra:
        txt_dir += f"<br/><font size=8>{safe(subtitulo_extra)}</font>"

    t = Table(
        [[cel_logo, Paragraph(txt_dir, est["titulo"])]],
        colWidths=[4.5 * cm, 14.3 * cm],
    )
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.75, est["cor_borda"]),
        ("LINEBEFORE", (1, 0), (1, 0), 0.5, est["cor_borda"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [t, Spacer(1, 3)]


def faixa_secao(titulo, est, largura=18.8 * cm):
    """Faixa cinza-claro P&B para títulos de seção, idêntica às barras da planilha."""
    t = Table([[Paragraph(safe(titulo), est["secao"])]], colWidths=[largura])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), est["cor_faixa"]),
        ("BOX", (0, 0), (-1, -1), 0.6, est["cor_borda"]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def tabela_pb(dados, col_widths, est, cabecalho_cinza=False, pad_v=2.2, pad_h=4):
    """Tabela limpa em P&B com fundo transparente para preservar a marca d'água."""
    t = Table(dados, colWidths=col_widths)
    regras = [
        ("GRID", (0, 0), (-1, -1), 0.5, est["cor_borda"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), pad_h),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad_h),
        ("TOPPADDING", (0, 0), (-1, -1), pad_v),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad_v),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
    ]
    if cabecalho_cinza:
        regras.extend([
            ("BACKGROUND", (0, 0), (-1, 0), est["cor_faixa"]),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    t.setStyle(TableStyle(regras))
    return t


def bloco_assinatura_padrao(est, local, data_dt, nome, cpf, rotulo="Assinatura do Proponente / Cliente", espaco_antes=12):
    """Bloco padronizado de Local/Data + Linha de assinatura + Nome e CPF formatado."""
    return [
        Spacer(1, espaco_antes),
        Paragraph(f"{safe(local)}, {fmt_data_extenso(data_dt)}.", est["centro"]),
        Spacer(1, 20),
        Paragraph("____________________________________________________________", est["centro"]),
        Paragraph(f"<b>{safe(nome)}</b>", est["centro"]),
        Paragraph(f"CPF/CNPJ: {fmt_doc(cpf)}", est["centro"]),
        Paragraph(safe(rotulo), ParagraphStyle("RotAssPB", parent=est["centro"], fontSize=7.2)),
    ]


# ============================================================================
# 1. NOVA PROPOSTA (PADRÃO FIEL DA PLANILHA — 1 FOLHA A4 P&B)
#    Inclui: Margem Crédito Pessoal separada, Parecer da Agência e 4 Assinaturas
# ============================================================================
def doc_nova_proposta(d, est):
    W = 18.8 * cm
    el = bloco_cabecalho_planilha("CARTA-PROPOSTA", est)

    # Linha Local/Data + Parceiro/Banco
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Local:</b> {safe(d.get('local_emissao'))}", est["normal"]),
            Paragraph(f"<b>Data:</b> {fmt_data_br(d.get('data_proposta'))}", est["normal"]),
            Paragraph(f"<b>Parceiro:</b> {safe(d.get('parceiro') or EMPRESA['nome_fantasia'])}", est["normal"]),
            Paragraph(f"<b>Banco:</b> {safe(d.get('banco_destino'))}", est["normal"]),
        ]
    ], [3.6 * cm, 3.0 * cm, 7.2 * cm, 5.0 * cm], est, pad_v=2))
    el.append(Spacer(1, 3))

    # DADOS DO CLIENTE
    el.append(faixa_secao("DADOS DO CLIENTE", est, W))
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>Enquadramento:</b> {safe(d.get('tipo_cliente'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
            Paragraph(f"<b>Telefone:</b> {safe(d.get('cliente_telefone'))}", est["normal"]),
        ],
    ], [11.8 * cm, 7.0 * cm], est, pad_v=2))
    el.append(Spacer(1, 3))

    # DADOS DA PROPRIEDADE BENEFICIADA E OPERAÇÃO
    el.append(faixa_secao("DADOS DA PROPRIEDADE BENEFICIADA", est, W))
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Imóvel Beneficiado:</b> {safe(d.get('imovel_beneficiado_texto'))}", est["normal"]),
            Paragraph(f"<b>CEP:</b> {fmt_cep(d.get('cep'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Rua:</b> {safe(d.get('rua'))}", est["normal"]),
            Paragraph(f"<b>Localidade:</b> {safe(d.get('localidade'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Cidade:</b> {safe(d.get('cidade'))} &nbsp;&nbsp;|&nbsp;&nbsp; <b>UF:</b> {safe(d.get('uf'))}", est["normal"]),
            Paragraph(f"<b>Bairro:</b> {safe(d.get('bairro'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Tipo de Serviço (Linha):</b> {safe(d.get('tipo_servico'))}", est["normal"]),
            Paragraph(f"<b>Item:</b> {safe(d.get('item_financiado'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Cultura:</b> {safe(d.get('cultura'))} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Carência:</b> {safe(d.get('carencia'))}", est["normal"]),
            Paragraph(f"<b>Valor Proposto:</b> <b>{fmt_moeda(d.get('valor_proposto'))}</b>", est["normal"]),
        ],
    ], [11.0 * cm, 7.8 * cm], est, pad_v=2))
    el.append(Spacer(1, 3))

    # DOCUMENTOS (3 COLUNAS: PROPONENTE | IMÓVEL | COOBRIGADOS)
    el.append(faixa_secao("DOCUMENTOS", est, W))
    chk = d.get("checklist_docs") or {}
    linhas_chk = [[
        Paragraph("<b>PROPONENTE</b>", est["micro"]),
        Paragraph("<b>IMÓVEL / CONTABILIDADE</b>", est["micro"]),
        Paragraph("<b>COOBRIGADOS</b>", est["micro"]),
    ]]

    # Monta coluna do meio exatamente como na planilha (4 docs imóvel + Contabilidade + Envio)
    col_meio = [
        f"[{'X' if chk.get('imov_' + item) else ' '}] {item}" for item in DOCS_IMOVEL
    ] + [
        "",
        f"<b>Contabilidade:</b> {safe(d.get('contabilidade_nome'))}",
        f"<b>CNPJ Contab.:</b> {fmt_doc(d.get('contabilidade_cnpj'))}",
        f"<b>Tipo de Envio:</b> {safe(d.get('tipo_envio_docs'))}",
        f"<b>Envio de Docs:</b> {safe(d.get('data_envio_docs')) or '___/___/______'}",
        f"<b>Vínculo Imóvel:</b> {safe(d.get('tipo_cliente'))}",
    ]
    max_len = max(len(DOCS_PROPONENTE), len(col_meio), len(DOCS_COOBRIGADOS))
    for i in range(max_len):
        c1 = f"[{'X' if chk.get('prop_' + DOCS_PROPONENTE[i]) else ' '}] {safe(DOCS_PROPONENTE[i])}" if i < len(DOCS_PROPONENTE) else ""
        c2 = col_meio[i] if i < len(col_meio) else ""
        c3 = f"[{'X' if chk.get('coob_' + DOCS_COOBRIGADOS[i]) else ' '}] {safe(DOCS_COOBRIGADOS[i])}" if i < len(DOCS_COOBRIGADOS) else ""
        linhas_chk.append([
            Paragraph(c1, est["micro"]),
            Paragraph(c2, est["micro"]),
            Paragraph(c3, est["micro"]),
        ])
    el.append(tabela_pb(linhas_chk, [7.0 * cm, 6.4 * cm, 5.4 * cm], est, cabecalho_cinza=True, pad_v=1.3))
    el.append(Spacer(1, 3))

    # MARGEM CRÉDITO PESSOAL (SEPARADA DE AVALISTAS!)
    el.append(faixa_secao("MARGEM CRÉDITO PESSOAL", est, W))
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Crédito:</b> {safe(d.get('credito_tipo')) or '—'}", est["normal"]),
            Paragraph(f"<b>Valor:</b> {fmt_moeda(d.get('credito_valor'))}", est["normal"]),
            Paragraph(f"<b>Benefício:</b> {fmt_moeda(d.get('beneficio_valor'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Parcela Consórcio:</b> {fmt_moeda(d.get('parcela_consorcio'))}", est["normal"]),
            Paragraph(f"<b>Nº Parcelas:</b> {int(d.get('num_parcelas_consorcio') or 0) or '—'}", est["normal"]),
            Paragraph("", est["normal"]),
        ],
    ], [6.6 * cm, 6.1 * cm, 6.1 * cm], est, pad_v=2))
    el.append(Spacer(1, 3))

    # PARECER DA AGÊNCIA BANCÁRIA (ESPAÇO DEDICADO COM ASS. AGÊNCIA)
    el.append(faixa_secao("PARECER DA AGÊNCIA BANCÁRIA", est, W))
    parecer_txt = safe(d.get("parecer_agencia", "")).replace("\n", "<br/>")
    if parecer_txt.strip():
        conteudo_parecer = Paragraph(parecer_txt, est["normal"])
    else:
        conteudo_parecer = Paragraph(
            "<br/><br/><br/>",
            est["normal"],
        )
    t_par = Table(
        [
            [conteudo_parecer],
            [Paragraph("Ass. Agência: _______________________________________", est["direita"])],
        ],
        colWidths=[W],
    )
    t_par.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, est["cor_borda"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    el.append(t_par)
    el.append(Spacer(1, 3))

    # ASSINATURAS (GRADE 2x2 EXATA CONFORME SOLICITADO NO ITEM 11):
    #   Coluna Esquerda: [1] Assinatura do Cliente + CPF | [2] Análise do Banco (Nome Legível)
    #   Coluna Direita (na frente): [1] Avalista + CPF   | [2] Cônjuge do Avalista + CPF
    el.append(faixa_secao("ASSINATURAS", est, W))

    def _cel_assinatura(rotulo, nome="", cpf="", sem_cpf=False):
        linhas = [
            "<br/>",
            "____________________________________________",
            f"<b>{safe(rotulo)}</b>",
        ]
        if not sem_cpf:
            linhas.append(f"Nome: {safe(nome) or '____________________________________'}")
            linhas.append(f"CPF/CNPJ: {fmt_doc(cpf) if cpf else '______________________________'}")
        else:
            linhas.append("Nome Legível: ________________________________")
            linhas.append("Matrícula / Carimbo: __________________________")
        return Paragraph("<br/>".join(linhas), est["centro"])

    t_ass = Table(
        [
            [
                _cel_assinatura("Assinatura do Cliente (Proponente)", d.get("cliente_nome"), d.get("cliente_cpf")),
                _cel_assinatura("Avalista", d.get("avalista_nome"), d.get("avalista_cpf")),
            ],
            [
                _cel_assinatura("Análise do Banco (Nome Legível)", sem_cpf=True),
                _cel_assinatura("Cônjuge do Avalista", d.get("conjuge_avalista_nome"), d.get("conjuge_avalista_cpf")),
            ],
        ],
        colWidths=[W / 2.0, W / 2.0],
    )
    t_ass.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, est["cor_borda"]),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(t_ass)
    return el


# ============================================================================
# 2. PRODUÇÃO / ANÁLISE PRODUTIVA (PADRÃO DA PLANILHA — 1 FOLHA A4 P&B)
# ============================================================================
def doc_producao(d, est):
    W = 18.8 * cm
    el = bloco_cabecalho_planilha("ANÁLISE PRODUTIVA", est)

    el.append(tabela_pb([
        [
            Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>Enquadramento:</b> {safe(d.get('tipo_cliente'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
            Paragraph(f"<b>Telefone:</b> {safe(d.get('cliente_telefone'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Localidade/Comunidade:</b> {safe(d.get('localidade'))}", est["normal"]),
            Paragraph(f"<b>Município/UF:</b> {safe(d.get('cidade'))} / {safe(d.get('uf'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Finalidade do Crédito:</b> {safe(d.get('tipo_servico'))} — {safe(d.get('item_financiado'))}", est["normal"]),
            Paragraph(f"<b>Valor Proposto:</b> <b>{fmt_moeda(d.get('valor_proposto'))}</b>", est["normal"]),
        ],
    ], [11.3 * cm, 7.5 * cm], est, pad_v=1.8))
    el.append(Spacer(1, 3))

    prod = d.get("dados_producao") or {}
    props = list(prod.get("propriedades") or [])
    # Exibe sempre 4 blocos (Beneficiada + 2, 3 e 4) no mesmo padrão visual da planilha
    while len(props) < 4:
        props.append({})

    el.append(faixa_secao("GARANTIAS E PRODUÇÃO POR PROPRIEDADE", est, W))
    for idx, p in enumerate(props[:4], start=1):
        rotulo = "Propriedade Beneficiada" if idx == 1 else f"Propriedade {idx}"
        bloco_p = tabela_pb([
            [
                Paragraph(f"<b>{rotulo}:</b> {safe(p.get('nome'))}", est["micro"]),
                Paragraph(f"<b>Matrícula:</b> {safe(p.get('matricula'))}", est["micro"]),
                Paragraph(f"<b>Nº Pés:</b> {safe(p.get('num_pes') or '')}", est["micro"]),
                Paragraph(f"<b>Espaçamento:</b> {safe(p.get('espacamento'))}", est["micro"]),
            ],
            [
                Paragraph(f"<b>Prev. 2027:</b> {safe(p.get('prev_2027'))} | <b>Prod. 2026:</b> {safe(p.get('prod_2026'))}", est["micro"]),
                Paragraph(f"<b>Venda 2026:</b> {fmt_moeda(p.get('venda_2026')) if p.get('venda_2026') else '—'}", est["micro"]),
                Paragraph(f"<b>Variedades:</b> {safe(p.get('variedades'))}", est["micro"]),
                Paragraph(f"<b>Idade:</b> {safe(p.get('idade'))}", est["micro"]),
            ],
            [
                Paragraph(f"<b>Prod. 2025:</b> {safe(p.get('prod_2025'))} | <b>Prod. 2024:</b> {safe(p.get('prod_2024'))}", est["micro"]),
                Paragraph(f"<b>Venda 2025:</b> {fmt_moeda(p.get('venda_2025')) if p.get('venda_2025') else '—'}", est["micro"]),
                Paragraph(f"<b>Venda 2024:</b> {fmt_moeda(p.get('venda_2024')) if p.get('venda_2024') else '—'}", est["micro"]),
                Paragraph("", est["micro"]),
            ],
        ], [6.4 * cm, 4.2 * cm, 4.6 * cm, 3.6 * cm], est, pad_v=1.5)
        el.append(bloco_p)
        el.append(Spacer(1, 2.5))

    sem = prod.get("semoventes") or {}
    el.append(faixa_secao("SEMOVENTES, RENDA EXTRA E BENS", est, W))
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Vacas de Leite:</b> {safe(sem.get('vacas_leite') or 0)}", est["micro"]),
            Paragraph(f"<b>Litros/Dia:</b> {safe(sem.get('litros_dia') or 0)}", est["micro"]),
            Paragraph(f"<b>Preço/Litro:</b> {fmt_moeda(sem.get('preco_litro'))}", est["micro"]),
        ],
        [
            Paragraph(f"<b>Boi de Corte:</b> {safe(sem.get('boi_corte') or 0)}", est["micro"]),
            Paragraph(f"<b>Novilhas:</b> {safe(sem.get('novilhas') or 0)}", est["micro"]),
            Paragraph(f"<b>Bezerros:</b> {safe(sem.get('bezerros') or 0)}", est["micro"]),
        ],
        [
            Paragraph(f"<b>Renda Extra 1:</b> {safe(prod.get('renda_extra_1_desc'))} ({fmt_moeda(prod.get('renda_extra_1_val'))})", est["micro"]),
            Paragraph(f"<b>Renda Extra 2:</b> {safe(prod.get('renda_extra_2_desc'))} ({fmt_moeda(prod.get('renda_extra_2_val'))})", est["micro"]),
            Paragraph(f"<b>RENDA BRUTA ANUAL: {fmt_moeda(d.get('renda_bruta_anual'))}</b>", est["micro"]),
        ],
        [
            Paragraph(f"<b>Bens:</b> {safe(prod.get('bens'))}", est["micro"]),
            Paragraph("", est["micro"]),
            Paragraph("", est["micro"]),
        ],
    ], [6.4 * cm, 6.2 * cm, 6.2 * cm], est, pad_v=1.8))

    el.extend(bloco_assinatura_padrao(
        est, d.get("local_emissao"), d.get("data_proposta"),
        d.get("cliente_nome"), d.get("cliente_cpf"),
        "Assinatura do Produtor Rural", espaco_antes=8,
    ))
    return el


# ============================================================================
# 3. ORDEM DE SERVIÇO (ITEM 7: VALOR CHEIO 2,00% + DESCONTO DA FAIXA — 1 FOLHA)
# ============================================================================
def doc_ordem_servico(d, est):
    W = 18.8 * cm
    el = bloco_cabecalho_planilha("ORDEM DE SERVIÇO", est)

    el.append(tabela_pb([
        [
            Paragraph(f"<b>Local:</b> {safe(d.get('local_emissao'))}", est["normal"]),
            Paragraph(f"<b>Data:</b> {fmt_data_br(d.get('data_proposta'))}", est["normal"]),
        ],
    ], [11.3 * cm, 7.5 * cm], est, pad_v=2))
    el.append(Spacer(1, 3))

    # Dados do Cliente
    el.append(faixa_secao("CLIENTE", est, W))
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Celular:</b> {safe(d.get('cliente_telefone'))}", est["normal"]),
            Paragraph(f"<b>Endereço/Localidade:</b> {safe(d.get('localidade') or d.get('rua'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Bairro:</b> {safe(d.get('bairro'))}", est["normal"]),
            Paragraph(f"<b>Cidade/UF:</b> {safe(d.get('cidade'))} / {safe(d.get('uf'))}", est["normal"]),
        ],
    ], [9.4 * cm, 9.4 * cm], est, pad_v=2))
    el.append(Spacer(1, 3))

    # Descrição do Serviço
    el.append(faixa_secao("DESCRIÇÃO DO SERVIÇO", est, W))
    el.append(tabela_pb([
        ["Item", "Linha / Serviço e Item Financiado", "Valor Proposto"],
        [
            "1",
            Paragraph(f"<b>{safe(d.get('tipo_servico'))}</b> — Item: {safe(d.get('item_financiado'))}", est["normal"]),
            Paragraph(f"<b>{fmt_moeda(d.get('valor_proposto'))}</b>", est["direita"]),
        ],
        [
            "2",
            Paragraph(safe(d.get("descricao_servico")), est["pequeno"]),
            Paragraph("—", est["centro"]),
        ],
    ], [1.2 * cm, 13.8 * cm, 3.8 * cm], est, cabecalho_cinza=True, pad_v=2.2))
    el.append(Spacer(1, 3))

    # Cláusulas OBS literais da planilha
    obs_lista = [
        "<b>OBS.:</b> O produtor terá que realizar o acerto (pagamento) da prestação dos serviços do ATER (escritório), na EMISSÃO DA MINUTA (contrato), onde já foram executados e finalizados os serviços do ATER (escritório).",
        "<b>OBS.:</b> Os serviços extras que são necessários executar no processo da operação de Crédito Rural assim solicitados pelo banco, terceiros e/ou próprio proponente, como: Licenças ou dispensas ambientais, CAR, Cartão de produtor, Contratos, Certidões e Levantamento Patrimonial (Pronamp BB), terão que realizar o ACERTO IMEDIATO, conforme a execução e entrega do documento pelo ATER (escritório).",
        "<b>OBS.:</b> Será cobrado do produtor o valor INTEGRAL dos serviços do ATER (escritório) conforme esta Ordem de Serviço. Em caso de desistência do produtor durante o processo de Crédito Rural, o pagamento será devido integralmente, visto que o serviço já foi executado.",
    ]
    for o in obs_lista:
        el.append(Paragraph(o, est["pequeno"]))
    el.append(Spacer(1, 4))

    # SERVIÇOS PRESTADOS — REGRA DO ITEM 7:
    # Mostra sempre o VALOR CHEIO (2,00%) nos honorários e o DESCONTO DA FAIXA no campo Desconto!
    val_prop = float(d.get("valor_proposto") or 0)
    val_cheio = float(d.get("valor_cheio_os") or round(val_prop * TAXA_HONORARIO_CHEIA, 2))
    pct_final = float(d.get("percentual_honorario") if d.get("percentual_honorario") is not None else TAXA_HONORARIO_CHEIA)
    pct_desc_faixa = max(0.0, round(TAXA_HONORARIO_CHEIA - pct_final, 6))
    desc_faixa = float(d.get("desconto_faixa") if d.get("desconto_faixa") is not None else round(val_prop * pct_desc_faixa, 2))
    desc_extra = float(d.get("desconto_extra") or 0.0)
    desc_total = round(desc_faixa + desc_extra, 2)
    acresc = float(d.get("acrescimos") or 0.0)
    total_os = max(0.0, round(val_cheio - desc_total + acresc, 2))
    n_parc = max(1, int(d.get("num_parcelas") or 1))
    val_parc = round(total_os / n_parc, 2)

    # Texto explicativo do desconto para mostrar claramente ao cliente o benefício concedido
    if desc_faixa > 0 and desc_extra > 0:
        rotulo_desc = f"Desconto Concedido (Faixa {pct_desc_faixa*100:.2f}% + Extra)"
    elif desc_faixa > 0:
        if pct_final == 0:
            rotulo_desc = "Desconto Concedido (Isenção — 2,00%)"
        else:
            rotulo_desc = f"Desconto Concedido ({pct_desc_faixa*100:.2f}% — Taxa final {pct_final*100:.2f}%)"
    elif desc_extra > 0:
        rotulo_desc = "Desconto Concedido"
    else:
        rotulo_desc = "Desconto"

    el.append(faixa_secao("SERVIÇOS PRESTADOS E CONDIÇÕES FINANCEIRAS", est, W))
    el.append(tabela_pb([
        ["Item", "Serviços Prestados", "Faixa Cheia", "Valor"],
        [
            "1",
            Paragraph("<b>PROJETO TÉCNICO</b> (Honorários Base — Valor Cheio 2,00%)", est["normal"]),
            Paragraph("2,00%", est["centro"]),
            Paragraph(fmt_moeda(val_cheio), est["direita"]),
        ],
    ], [1.2 * cm, 11.4 * cm, 2.4 * cm, 3.8 * cm], est, cabecalho_cinza=True, pad_v=2.2))

    # Bloco inferior espelhando exatamente as linhas Subtotal / Desconto / Acréscimos / TOTAL + Forma de Pagamento
    t_res = Table([
        [
            Paragraph(f"<b>Forma de Pagamento:</b> {safe(d.get('forma_pagamento'))}", est["normal"]),
            Paragraph("<b>Subtotal (Valor Cheio 2,00%)</b>", est["direita"]),
            Paragraph(fmt_moeda(val_cheio), est["direita"]),
        ],
        [
            Paragraph(f"<b>Parcelamento:</b> {n_parc} parcela(s) de <b>{fmt_moeda(val_parc)}</b>", est["normal"]),
            Paragraph(f"<b>{safe(rotulo_desc)}</b>", est["direita"]),
            Paragraph(f"- {fmt_moeda(desc_total)}" if desc_total > 0 else fmt_moeda(0), est["direita"]),
        ],
        [
            Paragraph(f"<i>Taxa efetiva aplicada ao cliente: <b>{pct_final*100:.2f}%</b></i>", est["micro"]),
            Paragraph("<b>Acréscimos</b>", est["direita"]),
            Paragraph(fmt_moeda(acresc), est["direita"]),
        ],
        [
            Paragraph("Autorizo os serviços, as taxas e os valores acima descritos.", est["normal_bold"]),
            Paragraph("<b>TOTAL A PAGAR</b>", est["direita_bold"]),
            Paragraph(f"<b>{fmt_moeda(total_os)}</b>", est["direita_bold"]),
        ],
    ], colWidths=[8.8 * cm, 6.2 * cm, 3.8 * cm])
    t_res.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, est["cor_borda"]),
        ("BACKGROUND", (1, 3), (2, 3), est["cor_faixa"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    el.append(t_res)

    # Assinaturas lado a lado (Cliente + Regularize) para caber em 1 página com folga
    el.append(Spacer(1, 14))
    t_ass_os = Table([
        [
            Paragraph(
                f"____________________________________________<br/>"
                f"<b>{safe(d.get('cliente_nome'))}</b><br/>"
                f"CPF/CNPJ: {fmt_doc(d.get('cliente_cpf'))}<br/>"
                f"<font size=7>Contratante / Produtor Rural</font>",
                est["centro"],
            ),
            Paragraph(
                f"____________________________________________<br/>"
                f"<b>{safe(EMPRESA['razao_social'].upper())}</b><br/>"
                f"CNPJ: {safe(EMPRESA['cnpj'])}<br/>"
                f"<font size=7>Contratada / Assessoria</font>",
                est["centro"],
            ),
        ]
    ], colWidths=[W / 2.0, W / 2.0])
    t_ass_os.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    el.append(t_ass_os)

    # Comprovante de Recebimento dos Serviços (idêntico às linhas 38-41 da planilha)
    el.append(Spacer(1, 8))
    el.append(faixa_secao("COMPROVANTE DE RECEBIMENTO DOS SERVIÇOS", est, W))
    el.append(tabela_pb([
        [
            Paragraph("Confirmo que o serviço foi prestado de acordo com o combinado.", est["normal"]),
            Paragraph("<b>Data de entrega do serviço:</b> ____/____/______", est["normal"]),
        ],
        [
            Paragraph("<br/>Assinatura do Cliente: _______________________________________________", est["normal"]),
            Paragraph("<br/>CPF: ________________________", est["normal"]),
        ],
    ], [11.8 * cm, 7.0 * cm], est, pad_v=3))
    return el


# ============================================================================
# 4. PROTEÇÃO DE DADOS — LGPD (1 FOLHA A4 P&B)
# ============================================================================
def doc_protecao_dados(d, est):
    el = bloco_cabecalho_planilha("TERMO DE CONSENTIMENTO PARA USO DE DADOS PESSOAIS E IMAGEM", est, "Lei nº 13.709/2018 — LGPD")
    p1 = (
        f"Pelo presente termo, autorizo a {EMPRESA['razao_social']}, CNPJ nº {EMPRESA['cnpj']}, "
        f"com sede na {EMPRESA['endereco_completo']}, telefones {EMPRESA['telefones']} e e-mail {EMPRESA['email']}, "
        "a tratar os dados pessoais e documentos fornecidos por mim ou obtidos junto ao escritório de contabilidade "
        "por mim indicado, exclusivamente para prestar os serviços solicitados: assessoria rural, organização e "
        "instrução de propostas de crédito rural, imobiliário ou comercial, regularização de imóveis e atividades relacionadas."
    )
    el.append(Paragraph(safe(p1), est["justificado"]))
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Contabilidade:</b> {safe(d.get('contabilidade_nome'))}", est["normal"]),
            Paragraph(f"<b>CNPJ Contabilidade:</b> {fmt_doc(d.get('contabilidade_cnpj'))}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Instituição Financeira:</b> {safe(d.get('banco_destino'))}", est["normal"]),
            Paragraph("<b>Abrangência:</b> Instituições financeiras e cooperativas", est["normal"]),
        ],
    ], [9.4 * cm, 9.4 * cm], est, pad_v=2.5))
    el.append(Spacer(1, 6))

    p2 = (
        "O tratamento pode incluir coleta, consulta, conferência, organização, armazenamento e compartilhamento "
        "estritamente necessário com o escritório de contabilidade indicado, instituições financeiras, cooperativas "
        "de crédito e órgãos públicos envolvidos no serviço solicitado, conforme a Lei nº 13.709/2018 (LGPD). "
        "Os dados serão utilizados apenas para essas finalidades e mantidos pelo período necessário à prestação dos "
        f"serviços e ao cumprimento de obrigações legais. O titular pode solicitar informações, correção ou exercer os "
        f"demais direitos previstos na LGPD pelo e-mail {EMPRESA['email']}."
    )
    p3 = (
        "SEGURANÇA GOV.BR: esta autorização NÃO permite acesso de terceiros à conta gov.br do titular. Senha, códigos "
        "temporários ou de recuperação, QR codes e outros fatores de autenticação são pessoais e não devem ser compartilhados. "
        "Quando uma análise depender de informações dessa conta, o próprio titular deverá acessá-la e fornecer os documentos "
        "necessários por meio seguro. A empresa não solicitará nem utilizará credenciais para se passar pelo titular."
    )
    p4 = (
        "Poderá também utilizar minha imagem (fotografia e/ou vídeo) exclusivamente em materiais institucionais e promocionais "
        "da empresa, inclusive em canais digitais. Esta autorização é facultativa, independente da contratação dos serviços e "
        f"pode ser recusada ou revogada a qualquer momento pelo e-mail {EMPRESA['email']}, sem prejuízo dos serviços. "
        "A imagem não será divulgada junto com documentos ou dados pessoais desnecessários."
    )
    el.append(Paragraph(safe(p2), est["justificado"]))
    el.append(Paragraph(f"<b>{safe(p3)}</b>", est["justificado"]))
    el.append(Paragraph(safe(p4), est["justificado"]))
    el.append(Spacer(1, 6))
    el.append(Paragraph("[  ] Li e aceito o tratamento dos meus dados para as finalidades descritas neste termo.", est["normal_bold"]))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), "Titular dos Dados"))
    return el


# ============================================================================
# 5. GALPÃO DE GRÃOS (1 FOLHA A4 P&B)
# ============================================================================
def doc_galpao_graos(d, est):
    el = bloco_cabecalho_planilha("GALPÃO PARA ARMAZENAGEM DE GRÃOS", est, "DECLARAÇÃO DO PROPONENTE")
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
        ],
    ], [11.8 * cm, 7.0 * cm], est, pad_v=2.5))
    el.append(Spacer(1, 8))
    for p in [
        "(1) O investimento solicitado será destinado à construção de um galpão de armazenagem de grãos.",
        "(2) A área destinada à armazenagem terá como finalidade única a guarda e conservação dos grãos, não sendo utilizada para beneficiamento, industrialização ou qualquer outro fim.",
        "(3) Comprometo-me a utilizar os recursos conforme informado, estando ciente de que qualquer destinação diversa poderá implicar em responsabilização civil, administrativa e/ou criminal, conforme a legislação vigente.",
        "(4) Declaro estar ciente de que a execução da obra será realizada sob minha total responsabilidade, incluindo a contratação de mão de obra, aquisição de materiais e observância das normas técnicas e legais aplicáveis, isentando a assessoria ou qualquer instituição financeira de qualquer responsabilidade relativa à execução da construção/reforma.",
        "Declaro ainda estar ciente de que a veracidade das informações aqui prestadas é de minha inteira responsabilidade.",
    ]:
        el.append(Paragraph(safe(p), est["justificado"]))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


# ============================================================================
# 6 a 23. FORMULÁRIOS BANCÁRIOS (TODOS EM P&B, 1 FOLHA A4 CADA)
# ============================================================================
def doc_autorizacao_compartilhamento(d, est, banco_nome, parceira_txt):
    el = bloco_cabecalho_planilha(f"AUTORIZAÇÃO PARA COMPARTILHAMENTO — {banco_nome.upper()}", est, "Agronegócios")
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Proponente:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
        ],
    ], [11.8 * cm, 7.0 * cm], est, pad_v=2.5))
    el.append(Spacer(1, 10))
    el.append(faixa_secao("DECLARAÇÃO", est, 18.8 * cm))
    el.append(Spacer(1, 6))
    t1 = (
        f"Autorizo {parceira_txt} a fornecer à empresa {EMPRESA['razao_social'].upper()}, CNPJ: {EMPRESA['cnpj']}, "
        "parceira no acolhimento de proposta de Agronegócios, as informações registradas em meu cadastro relativas "
        "aos meus dados pessoais, profissionais e residenciais, bem como referentes a imóveis urbanos ou rurais "
        "de minha propriedade, sem menção a valor econômico."
    )
    t2 = (
        f"As informações, cujo fornecimento é autorizado, deverão ser utilizadas exclusivamente para fins de instruir "
        f"a minha proposta de Agronegócios junto a {banco_nome}, não podendo contemplar informação de saldo de operações "
        "ativas ou passivas de minha responsabilidade."
    )
    el.append(Paragraph(safe(t1), est["justificado"]))
    el.append(Paragraph(safe(t2), est["justificado"]))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_sicoob_bndes(d, est):
    el = bloco_cabecalho_planilha("PROPOSTA PARA OS PROGRAMAS DO BNDES", est, f"SICOOB — Singular: {EMPRESA['sicoob_singular']}")
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Nome do Cooperado:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
        ],
    ], [11.8 * cm, 7.0 * cm], est, pad_v=2))
    el.append(Spacer(1, 5))
    el.append(faixa_secao("DECLARAÇÃO E AUTORIZAÇÃO DO PROPONENTE", est, 18.8 * cm))
    el.append(Spacer(1, 4))
    textos = [
        "<b>Autorização para consulta ao Sicor:</b> Quando se tratar de operação de Crédito Rural, autorizo o Credor a: (i) consultar o Sistema de Operações do Crédito Rural e do Proagro (Sicor), gerido pelo Banco Central do Brasil, para a obtenção de dados e informações cadastrais necessários à análise e concessão do crédito e enquadramento de garantias, autorização estendida às demais instituições autorizadas; e (ii) ter acesso aos dados registrados no Sicor sobre operações ativas e passivas e serviços prestados por instituições financeiras. Declaro ciência de que o Sicor se destina ao registro das operações de crédito rural e enquadramentos no Proagro.",
        "<b>Declaração para PRONAMP ou Moderfrota PRONAMP:</b> Declaro ao Sicoob ter, no mínimo, 80% (oitenta por cento) da renda bruta anual originária da atividade agropecuária.",
        "<b>Declaração Programa Fundo Clima:</b> Declaro ao Sicoob que, para os casos em que houver previsão de redução do quadro de pessoal, estou ciente da recomendação para implementação de programas de qualificação e requalificação profissional com princípios de transição justa e políticas inclusivas.",
        "<b>Inexistência de impedimento junto ao Sistema BNDES:</b> Declaro ao Sicoob que não possuo impedimentos à realização de transações com o Sistema BNDES, não estando listado(a) nas vedações da Política para Transações com Partes Relacionadas do Sistema BNDES.",
        "<b>Operações de Pronaf Investimento:</b> Declaro ao Sicoob que, em caso de possuir operação(ões) contratada(s) de PRONAF Investimento em qualquer instituição integrante do SNCR, eu as discriminarei abaixo (individuais e grupais/coletivas), ciente das sanções legais e do MCR em caso de declaração falsa.",
    ]
    for t in textos:
        el.append(Paragraph(t, est["pequeno"]))
    el.append(Spacer(1, 4))
    el.append(tabela_pb([
        ["Programa", "Finalidade / Item", "Contratação", "Vencimento", "Valor"],
        [safe(d.get("tipo_servico")), safe(d.get("item_financiado")), "", "", fmt_moeda(d.get("valor_proposto"))],
    ], [4.8 * cm, 4.8 * cm, 3.0 * cm, 3.0 * cm, 3.2 * cm], est, cabecalho_cinza=True, pad_v=2.2))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), espaco_antes=10))
    return el


def doc_consulta_bacen_cooperativa(d, est, cooperativa_nome):
    el = bloco_cabecalho_planilha("AUTORIZAÇÃO PARA CONSULTA AO BANCO CENTRAL", est, cooperativa_nome)
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
        ],
    ], [11.8 * cm, 7.0 * cm], est, pad_v=2.5))
    el.append(Spacer(1, 8))
    for p in [
        f"Autorizamos o {cooperativa_nome} a consultar as informações consolidadas, relativas a nossos nomes e da empresa em que somos sócios, constantes do Sistema Central de Risco de Crédito do BACEN.",
        f"Autorizamos, ainda, o {cooperativa_nome} a fornecer informações sobre as operações de crédito com ela realizadas, no sentido de compor o cadastro do já citado Sistema.",
        "Os presentes dados são verdadeiros e visam facilitar os processos de negociação e transações comerciais, pela antecipação de informações a nosso respeito.",
        "Autorizamos o arquivamento dos nossos dados pessoais e de idoneidade na SERASA – Centralização de Serviços dos Bancos S/A e/ou SPC/CDL – Serviço de Proteção ao Crédito, que poderá deles se utilizar, respeitadas as disposições legais em vigor.",
    ]:
        el.append(Paragraph(safe(p), est["justificado"]))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_termo_sicoob(d, est):
    el = bloco_cabecalho_planilha("TERMO DE AUTORIZAÇÃO PARA CONSULTA DOS DADOS NO SICOR / PROAGRO", est, "SICOOB")
    t1 = (
        f"Através do presente instrumento, eu <b>{safe(d.get('cliente_nome'))}</b>, inscrito(a) no CPF/CNPJ sob nº "
        f"<b>{fmt_doc(d.get('cliente_cpf'))}</b>, autorizo a cooperativa de crédito de meu relacionamento a consultar o "
        "Sistema de Operações do Crédito Rural e do Proagro (Sicor), gerido pelo Banco Central do Brasil, para a obtenção "
        "de dados e informações pessoais/cadastrais necessários à análise de concessão do crédito e enquadramento de garantias, "
        "bem como a ter acesso aos dados registrados no Sicor sobre minhas operações de crédito rural e Proagro contratadas em instituições financeiras."
    )
    t2 = (
        "A presente autorização fica estendida, desde já, ao Banco Cooperativo do Sicoob S.A - Banco Sicoob, "
        "à Confederação Nacional das Cooperativas do Sicoob LTDA. - Sicoob Confederação e às demais cooperativas "
        "de crédito integrantes do Sistema de Cooperativas Financeiras do Brasil - Sicoob."
    )
    t3 = (
        "Ainda, declaro ciência que o Sicor possui o registro das operações de crédito rural concedidas pelas instituições "
        "financeiras autorizadas a operar em crédito rural, bem como dos enquadramentos de empreendimentos no Programa de Garantia da Atividade Agropecuária (Proagro)."
    )
    el.append(Paragraph(t1, est["justificado"]))
    el.append(Paragraph(safe(t2), est["justificado"]))
    el.append(Paragraph(safe(t3), est["justificado"]))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_bb_scr(d, est, nome_assinante, cpf_assinante, rotulo):
    el = bloco_cabecalho_planilha("AUTORIZAÇÃO PARA COMPARTILHAMENTO DE DADOS CADASTRAIS E CONSULTA AO SCR", est, f"BANCO DO BRASIL — {rotulo.upper()}")
    for p in [
        f"Autorizo o Banco do Brasil S.A. a fornecer às empresas {EMPRESA['razao_social']}, CNPJ: {EMPRESA['cnpj']} e Cobra Tecnologia S/A, CNPJ 42.318.949/0001-84, parceiras do Banco do Brasil S.A. no acolhimento e análise de proposta, informações registradas em meu cadastro relativas aos meus dados pessoais, profissionais e residenciais, bem como referentes a imóveis urbanos ou rurais de minha propriedade, sem menção a valor econômico.",
        "As informações, cujo fornecimento é autorizado, deverão ser utilizadas exclusivamente para fins de instruir a minha proposta de crédito junto ao Banco do Brasil S.A., não podendo contemplar informação de saldo de operações ativas ou passivas de minha responsabilidade.",
        "Autorizo, ainda, o conglomerado Banco do Brasil S.A. a consultar os débitos e responsabilidades decorrentes de operações com características de crédito e as informações e os registros de medidas judiciais que em meu nome constem ou venham a constar do Sistema de Informações de Crédito (SCR), gerido pelo Banco Central do Brasil - Bacen, ou dos sistemas que venham a complementá-lo ou a substituí-lo.",
        "Estou ciente de que: a) o SCR tem por finalidades fornecer informações ao Bacen para fins de supervisão do risco de crédito e propiciar o intercâmbio de informações entre instituições financeiras; b) poderei ter acesso aos dados constantes em meu nome no SCR por meio da Central de Atendimento ao Público do Banco Central do Brasil (CAP); c) pedidos de correções, de exclusões e de manifestações de discordância quanto às informações constantes do SCR deverão ser dirigidas ao Bacen ou à instituição responsável pela remessa das informações; d) a consulta sobre qualquer informação ao SCR depende de minha prévia autorização; e) mais informações podem ser obtidas em www.bcb.gov.br ou www.bb.com.br.",
    ]:
        el.append(Paragraph(safe(p), est["pequeno"]))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), nome_assinante, cpf_assinante, rotulo, espaco_antes=10))
    el.append(Spacer(1, 8))
    el.append(Paragraph(
        "Telefones BB: Central de Atendimento 4004-0001 / 0800-729-0001 | SAC 0800-729-0722 | Deficientes Auditivos/Fala 0800-729-0088 | Ouvidoria BB 0800-729-5678.",
        est["micro"],
    ))
    return el


def doc_sicor(d, est, nome_assinante, cpf_assinante, rotulo):
    el = bloco_cabecalho_planilha("AUTORIZAÇÃO PARA CONSULTA AO SICOR", est, f"BANCO DO BRASIL — {rotulo.upper()}")
    el.append(Paragraph(
        "Autorizo(amos) o conglomerado Banco do Brasil S.A. (BB) a consultar o Sistema de Operações de Crédito Rural e do Proagro (SICOR), "
        "gerido pelo Bacen, a respeito de informações referentes a operações de crédito rural e Proagro que eu(nós) possuo(ímos) junto a "
        "qualquer instituição financeira integrante do Sistema Nacional de Crédito Rural (SNCR). Estou(amos) ciente(s) de que:",
        est["pequeno"],
    ))
    for a in [
        "a) o SICOR tem por finalidade prover o Bacen de informações sobre dados de crédito rural e operações enquadradas no Proagro para fins de monitoramento e fiscalização, nos termos do Manual de Crédito Rural, bem como propiciar o intercâmbio de informações entre instituições financeiras definidas no §1º do artigo 1º da Lei Complementar nº 105/2001;",
        "b) a consulta sobre qualquer informação registrada no SICOR depende de minha(nossa) prévia autorização;",
        "c) poderei(emos) ter acesso aos dados constantes em meu(nosso) nome no SICOR por meio do sistema Registrato do Bacen;",
        "d) pedidos de correções, exclusões e manifestações de discordância quanto às informações constantes do SICOR deverão ser dirigidos ao BB, por meio de requerimento escrito e fundamentado, ou pela respectiva decisão judicial, quando o BB tiver sido o responsável pelo envio;",
        "e) o Conglomerado Banco do Brasil é obrigado a enviar para registro no SICOR/Bacen as informações sobre operações de crédito rural e Proagro contratadas e a serem contratadas por mim(nós);",
        "f) mais informações sobre o SICOR podem ser obtidas em www.bcb.gov.br ou www.bb.com.br.",
    ]:
        el.append(Paragraph(safe(a), est["pequeno"]))
    el.append(Paragraph(
        "Por fim, declaro(amos) ciente(s) de que a consulta supracitada, por implicar tratamento de meus(nossos) dados pessoais, "
        "ocorrerá em conformidade com a Lei nº 13.709/2018 (LGPD) e demais normas aplicáveis, visando procedimentos preliminares "
        "relacionados a eventual contratação solicitada e cumprimento de obrigações legais ou regulatórias.",
        est["pequeno"],
    ))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), nome_assinante, cpf_assinante, rotulo, espaco_antes=10))
    return el


def doc_bradesco(d, est):
    el = bloco_cabecalho_planilha("AUTORIZAÇÃO PARA CONSULTA AO SICOR — BANCO BRADESCO S/A", est)
    el.append(Paragraph("Ao Banco Bradesco S/A,", est["normal"]))
    el.append(Spacer(1, 8))
    el.append(Paragraph(
        "Em razão de estar/estarmos pleiteando financiamento de crédito rural, autorizo(amos) o Banco Bradesco S/A "
        "a acessar os dados registrados no SICOR - Sistema de Operações do Crédito Rural e do Proagro, sobre operações "
        "ativas e passivas e serviços prestados por instituições financeiras, bem como demais informações pessoais que "
        "serão exibidas por tais consultas.",
        est["justificado"],
    ))
    el.append(Spacer(1, 6))
    el.append(Paragraph("Atenciosamente,", est["normal"]))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_caixa(d, est):
    el = bloco_cabecalho_planilha("AUTORIZAÇÃO DE CONSULTA AO SCR E SICOR — CAIXA ECONÔMICA FEDERAL", est)
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Nome Completo:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
        ],
    ], [11.8 * cm, 7.0 * cm], est, pad_v=2.5))
    el.append(Spacer(1, 10))
    el.append(Paragraph(
        "Declaro que AUTORIZO, nos termos da Resolução CMN nº 3.658, de 17/12/2008, a CAIXA ECONÔMICA FEDERAL "
        "a consultar as informações consolidadas relativas à minha pessoa, constantes no Sistema de Informações de "
        "Créditos (SCR) e no Sistema de Operações do Crédito Rural e do Proagro (Sicor), ambos do BACEN.",
        est["justificado"],
    ))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_invest_caixa(d, est):
    el = bloco_cabecalho_planilha("DECLARAÇÃO DE RENEGOCIAÇÕES POR RESOLUÇÕES DO CMN", est, "CAIXA ECONÔMICA FEDERAL — Grau de Sigilo #00")
    el.append(tabela_pb([
        [
            Paragraph(f"<b>Cód. Agência:</b> {safe(EMPRESA['caixa_cod_agencia'])}", est["normal"]),
            Paragraph(f"<b>Nome da Agência:</b> {safe(EMPRESA['caixa_nome_agencia'])}", est["normal"]),
        ],
        [
            Paragraph(f"<b>Nome/Razão Social:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
            Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
        ],
    ], [9.4 * cm, 9.4 * cm], est, pad_v=2))
    el.append(Spacer(1, 4))
    el.append(Paragraph("[  ] Declaro, sob as penas da lei, que NÃO POSSUO operação(ões) de Crédito Rural ativa(s) renegociada(s) com base nas Resoluções do CMN descritas abaixo.", est["pequeno"]))
    el.append(Paragraph("[  ] Declaro, sob as penas da lei, que POSSUO operação(ões) de Crédito Rural ativa(s) renegociada(s) com base nas Resoluções do CMN descritas abaixo:", est["pequeno"]))
    el.append(Spacer(1, 3))

    resolucoes = [
        ("Resolução CMN nº 4.504 (01/07/2016)", "Operações de crédito rural da cultura do arroz na região Sul (emergência/calamidade pública) — safra 2015/2016 e parcelas 2016 (MCR 6-2, 6-4, IHCD, BNDES, PRONAF)."),
        ("Resolução CMN nº 4.508 (28/07/2016)", "Operações de crédito rural da cultura da soja no RS (emergência/calamidade pública) — safra 2015/2016 e parcelas 2016 (MCR 6-2)."),
        ("Resolução CMN nº 4.519 (14/09/2016)", "Custeio e investimento com prejuízos de seca/estiagem em ES, BA, PI, MA, TO e Centro-Oeste (adimplentes em 31/12/2015, MCR 6-1-2)."),
        ("Resolução CMN nº 4.522 (29/09/2016)", "Custeio e investimento destinados à cultura de café no ES (seca/estiagem), adimplentes em 31/12/2014, vencidas entre 01/01/2015 e 31/12/2016 (MCR 6-1-2)."),
        ("Resolução CMN nº 4.565 (27/04/2017)", "Custeio e investimento na área da SUDENE (seca/estiagem), adimplentes em 31/12/2015, vencidas de 01/01/2016 a 29/12/2017 (MCR 6-1-2)."),
        ("Resolução CMN nº 4.568 (26/05/2017)", "Custeio e investimento na área da SUDENE com recursos MCR 6-2, adimplentes em 31/12/2015, vencidas de 01/01/2016 a 29/12/2017."),
        ("Resolução CMN nº 4.591 (25/07/2017)", "Custeio e investimento na área da SUDENE contratadas de 01/01/2012 a 31/12/2016 (recursos controlados MCR 6-1-2)."),
        ("Resolução CMN nº 4.660 (17/05/2018)", "Custeio e investimento contratadas até 31/12/2016 na área da SUDENE e no Estado do Espírito Santo (MCR 6-1-2)."),
    ]
    linhas_res = [["Resolução", "Enquadramento"]] + [
        [Paragraph(f"<b>{safe(r)}</b>", est["micro"]), Paragraph(safe(desc), est["micro"])]
        for r, desc in resolucoes
    ]
    el.append(tabela_pb(linhas_res, [5.0 * cm, 13.8 * cm], est, cabecalho_cinza=True, pad_v=1.8))
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        "Estou(amos) ciente(s) de que declaração falsa implica substituição, desde a data da contratação, da taxa de juros "
        "pactuada por taxa de mercado, sem prejuízo das demais sanções e penalidades previstas em lei e no Manual de Crédito Rural – MCR.",
        est["pequeno"],
    ))
    el.extend(bloco_assinatura_padrao(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), "Cliente ou Representante Legal", espaco_antes=8))
    return el


# ============================================================================
# ROTEADOR CENTRAL: MONTA 1 DOCUMENTO OU PACOTE COMPLETO (1 FOLHA POR DOC)
# ============================================================================
def gerar_pdf_bytes(dados_proposta, lista_documentos):
    """
    Gera um arquivo PDF em preto e branco com marca d'água da Regularize em
    todas as páginas, garantindo exatamente 1 folha A4 por documento.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.1 * cm,
        rightMargin=1.1 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
        title="Sistema Carta-Proposta - Regularize Assessoria Rural",
        author=EMPRESA["razao_social"],
    )
    est = criar_estilos_pb()
    story = []

    for idx, nome_doc in enumerate(lista_documentos):
        if idx > 0:
            story.append(PageBreak())

        if nome_doc == "NOVA PROPOSTA":
            story.extend(doc_nova_proposta(dados_proposta, est))
        elif nome_doc == "PRODUÇÃO":
            story.extend(doc_producao(dados_proposta, est))
        elif nome_doc == "ORDEM DE SERVIÇO":
            story.extend(doc_ordem_servico(dados_proposta, est))
        elif nome_doc == "PROTEÇÃO DE DADOS":
            story.extend(doc_protecao_dados(dados_proposta, est))
        elif nome_doc == "GALPÃO DE GRÃOS":
            story.extend(doc_galpao_graos(dados_proposta, est))
        elif nome_doc == "SICOOB BNDES":
            story.extend(doc_sicoob_bndes(dados_proposta, est))
        elif nome_doc == "AUTORIZAÇÃO SICOOB":
            story.extend(doc_autorizacao_compartilhamento(dados_proposta, est, "Sicoob", "o Sicoob"))
        elif nome_doc == "SICOOB":
            story.extend(doc_consulta_bacen_cooperativa(dados_proposta, est, EMPRESA["sicoob_cooperativa"]))
        elif nome_doc == "TERMO SICOOB":
            story.extend(doc_termo_sicoob(dados_proposta, est))
        elif nome_doc == "B. DO BRASIL":
            story.extend(doc_bb_scr(dados_proposta, est, dados_proposta.get("cliente_nome"), dados_proposta.get("cliente_cpf"), "Proponente"))
        elif nome_doc == "AUTORIZAÇÃO BB":
            story.extend(doc_autorizacao_compartilhamento(dados_proposta, est, "Banco do Brasil", "ao Banco do Brasil"))
        elif nome_doc == "BB AVAL":
            story.extend(doc_bb_scr(dados_proposta, est, dados_proposta.get("avalista_nome"), dados_proposta.get("avalista_cpf"), "Avalista"))
        elif nome_doc == "BB CONJUGE AVAL":
            story.extend(doc_bb_scr(dados_proposta, est, dados_proposta.get("conjuge_avalista_nome"), dados_proposta.get("conjuge_avalista_cpf"), "Cônjuge Avalista"))
        elif nome_doc == "SICOR":
            story.extend(doc_sicor(dados_proposta, est, dados_proposta.get("cliente_nome"), dados_proposta.get("cliente_cpf"), "Proponente"))
        elif nome_doc == "SICOR AVAL":
            story.extend(doc_sicor(dados_proposta, est, dados_proposta.get("avalista_nome"), dados_proposta.get("avalista_cpf"), "Avalista"))
        elif nome_doc == "SICOR CONJUGE AVAL":
            story.extend(doc_sicor(dados_proposta, est, dados_proposta.get("conjuge_avalista_nome"), dados_proposta.get("conjuge_avalista_cpf"), "Cônjuge Avalista"))
        elif nome_doc == "BRADESCO":
            story.extend(doc_bradesco(dados_proposta, est))
        elif nome_doc == "AUTORIZAÇÃO BRADESCO":
            story.extend(doc_autorizacao_compartilhamento(dados_proposta, est, "Banco Bradesco", "o Banco Bradesco"))
        elif nome_doc == "CRESOL":
            story.extend(doc_consulta_bacen_cooperativa(dados_proposta, est, EMPRESA["cresol_cooperativa"]))
        elif nome_doc == "AUTORIZAÇÃO CRESOL":
            story.extend(doc_autorizacao_compartilhamento(dados_proposta, est, "Cresol", "a Cresol"))
        elif nome_doc == "CAIXA":
            story.extend(doc_caixa(dados_proposta, est))
        elif nome_doc == "AUTORIZAÇÃO CAIXA":
            story.extend(doc_autorizacao_compartilhamento(dados_proposta, est, "Caixa Econômica Federal", "a Caixa Econômica Federal"))
        elif nome_doc == "INVEST CAIXA":
            story.extend(doc_invest_caixa(dados_proposta, est))

    doc.build(
        story,
        onFirstPage=desenhar_marca_dagua_e_rodape,
        onLaterPages=desenhar_marca_dagua_e_rodape,
    )
    return buffer.getvalue()
