# ============================================================================
# ARQUIVO: pdf_generator.py
# O QUE ESTE ARQUIVO FAZ:
#   Gera TODOS os 23 documentos em PDF exatamente como a sua planilha Excel
#   fazia (Carta-Proposta, Análise Produtiva, Ordem de Serviço, LGPD,
#   Galpão de Grãos e todos os termos do Sicoob, Banco do Brasil, SICOR,
#   Bradesco, Cresol e Caixa).
#
#   Você NÃO precisa mexer neste arquivo — ele lê os dados da empresa
#   automaticamente do arquivo config.py e os dados do cliente do banco.
# ============================================================================

import io
from datetime import date, datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import EMPRESA, DOCS_PROPONENTE, DOCS_IMOVEL, DOCS_COOBRIGADOS


# ============================================================================
# FUNÇÕES DE FORMATAÇÃO (MOEDA, CPF/CNPJ E DATA NO PADRÃO BRASILEIRO)
# ============================================================================
def fmt_moeda(valor):
    """Transforma 500000 em 'R$ 500.000,00'."""
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0.0
    texto = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def fmt_doc(cpf_cnpj):
    """Formata CPF (000.000.000-00) ou CNPJ (00.000.000/0000-00)."""
    d = "".join(ch for ch in str(cpf_cnpj or "") if ch.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return str(cpf_cnpj or "")


def fmt_data_extenso(dt=None):
    """Retorna data no formato '24 de novembro de 2026'."""
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
    """Retorna data no formato '24/11/2026'."""
    if not dt:
        dt = date.today()
    elif isinstance(dt, str):
        try:
            dt = datetime.strptime(dt[:10], "%Y-%m-%d").date()
        except ValueError:
            return dt
    return dt.strftime("%d/%m/%Y")


def safe(texto):
    """Protege caracteres especiais (&, <, >) para não quebrar o gerador de PDF."""
    return escape(str(texto or ""))


# ============================================================================
# ESTILOS VISUAIS DOS DOCUMENTOS PDF
# ============================================================================
def criar_estilos():
    base = getSampleStyleSheet()
    cor_primaria = colors.HexColor("#1B4332")  # Verde escuro institucional
    cor_borda = colors.HexColor("#CBD5E1")
    cor_fundo_suave = colors.HexColor("#F1F5F9")

    estilos = {
        "cor_primaria": cor_primaria,
        "cor_borda": cor_borda,
        "cor_fundo": cor_fundo_suave,
        "titulo": ParagraphStyle(
            "TituloDoc", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=13, leading=16, alignment=TA_CENTER, textColor=cor_primaria,
            spaceAfter=8,
        ),
        "subtitulo": ParagraphStyle(
            "SubtituloDoc", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=10, leading=13, alignment=TA_LEFT, textColor=cor_primaria,
            spaceBefore=6, spaceAfter=4,
        ),
        "normal": ParagraphStyle(
            "NormalDoc", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=12.5, alignment=TA_LEFT,
        ),
        "justificado": ParagraphStyle(
            "JustificadoDoc", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=13, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "pequeno": ParagraphStyle(
            "PequenoDoc", parent=base["Normal"], fontName="Helvetica",
            fontSize=7.5, leading=10, alignment=TA_JUSTIFY, spaceAfter=4,
        ),
        "centro": ParagraphStyle(
            "CentroDoc", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=12, alignment=TA_CENTER,
        ),
        "centro_bold": ParagraphStyle(
            "CentroBoldDoc", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9, leading=12, alignment=TA_CENTER,
        ),
        "direita": ParagraphStyle(
            "DireitaDoc", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=12, alignment=TA_RIGHT,
        ),
    }
    return estilos


def bloco_cabecalho(titulo, est, subtitulo_extra=""):
    """Cabeçalho padrão com nome da Regularize + título do documento."""
    itens = [
        Paragraph(f"<b>{safe(EMPRESA['razao_social'].upper())}</b>", est["centro"]),
        Paragraph(
            f"CNPJ: {safe(EMPRESA['cnpj'])} | {safe(EMPRESA['telefones'])} | {safe(EMPRESA['email'])}",
            ParagraphStyle("CabInfo", parent=est["centro"], fontSize=7.5, textColor=colors.grey),
        ),
        Spacer(1, 4),
        Paragraph(safe(titulo), est["titulo"]),
    ]
    if subtitulo_extra:
        itens.append(Paragraph(safe(subtitulo_extra), est["centro_bold"]))
    itens.append(Spacer(1, 6))
    return itens


def bloco_assinatura(est, local, data_dt, nome, cpf, rotulo="Assinatura do Proponente / Cliente"):
    """Bloco padronizado de Local/Data + Linha de assinatura + Nome e CPF."""
    return [
        Spacer(1, 14),
        Paragraph(f"{safe(local)}, {fmt_data_extenso(data_dt)}.", est["centro"]),
        Spacer(1, 24),
        Paragraph("____________________________________________________________", est["centro"]),
        Paragraph(f"<b>{safe(nome)}</b>", est["centro"]),
        Paragraph(f"CPF/CNPJ: {fmt_doc(cpf)}", est["centro"]),
        Paragraph(safe(rotulo), ParagraphStyle("RotAss", parent=est["centro"], fontSize=7.5, textColor=colors.grey)),
    ]


def tabela_simples(dados, col_widths, est, cabecalho_colorido=False):
    """Helper para desenhar tabelas com bordas finas e visual limpo."""
    t = Table(dados, colWidths=col_widths)
    regras = [
        ("GRID", (0, 0), (-1, -1), 0.5, est["cor_borda"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ]
    if cabecalho_colorido:
        regras.extend([
            ("BACKGROUND", (0, 0), (-1, 0), est["cor_primaria"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ])
    t.setStyle(TableStyle(regras))
    return t


# ============================================================================
# GERADORES DOS 23 DOCUMENTOS OFICIAIS (1 FUNÇÃO POR ABA DA PLANILHA ORIGINAL)
# ============================================================================

def doc_nova_proposta(d, est):
    el = bloco_cabecalho("CARTA-PROPOSTA DE CRÉDITO RURAL", est)

    # Cabeçalho de emissão
    el.append(tabela_simples([
        [Paragraph(f"<b>Local:</b> {safe(d.get('local_emissao'))}", est["normal"]),
         Paragraph(f"<b>Data:</b> {fmt_data_br(d.get('data_proposta'))}", est["normal"])],
        [Paragraph(f"<b>Parceiro:</b> {safe(d.get('parceiro') or EMPRESA['nome_fantasia'])}", est["normal"]),
         Paragraph(f"<b>Banco Destino:</b> {safe(d.get('banco_destino'))}", est["normal"])],
    ], [9 * cm, 9 * cm], est))
    el.append(Spacer(1, 6))

    # Dados do Cliente
    el.append(Paragraph("DADOS DO CLIENTE", est["subtitulo"]))
    el.append(tabela_simples([
        [Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>Tipo:</b> {safe(d.get('tipo_cliente'))}", est["normal"])],
        [Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
         Paragraph(f"<b>Telefone:</b> {safe(d.get('cliente_telefone'))}", est["normal"])],
    ], [11 * cm, 7 * cm], est))

    # Dados da Propriedade Beneficiada
    el.append(Paragraph("DADOS DA PROPRIEDADE BENEFICIADA E OPERAÇÃO", est["subtitulo"]))
    el.append(tabela_simples([
        [Paragraph(f"<b>Imóvel Beneficiado:</b> {safe(d.get('imovel_beneficiado_texto'))}", est["normal"]),
         Paragraph(f"<b>CEP:</b> {safe(d.get('cep'))}", est["normal"])],
        [Paragraph(f"<b>Rua:</b> {safe(d.get('rua'))}", est["normal"]),
         Paragraph(f"<b>Localidade:</b> {safe(d.get('localidade'))}", est["normal"])],
        [Paragraph(f"<b>Cidade/UF:</b> {safe(d.get('cidade'))} / {safe(d.get('uf'))}", est["normal"]),
         Paragraph(f"<b>Bairro:</b> {safe(d.get('bairro'))}", est["normal"])],
        [Paragraph(f"<b>Tipo de Serviço:</b> {safe(d.get('tipo_servico'))}", est["normal"]),
         Paragraph(f"<b>Item:</b> {safe(d.get('item_financiado'))}", est["normal"])],
        [Paragraph(f"<b>Cultura:</b> {safe(d.get('cultura'))}", est["normal"]),
         Paragraph(f"<b>Carência:</b> {safe(d.get('carencia'))}", est["normal"])],
        [Paragraph(f"<b>Valor Proposto:</b> {fmt_moeda(d.get('valor_proposto'))}", est["normal"]),
         Paragraph(f"<b>Contabilidade:</b> {safe(d.get('contabilidade_nome'))}", est["normal"])],
    ], [10.5 * cm, 7.5 * cm], est))

    # Checklist de Documentos
    el.append(Paragraph("CHECKLIST DE DOCUMENTOS", est["subtitulo"]))
    chk = d.get("checklist_docs") or {}
    linhas_chk = [[
        Paragraph("<b>PROPONENTE</b>", est["normal"]),
        Paragraph("<b>IMÓVEL</b>", est["normal"]),
        Paragraph("<b>COOBRIGADOS</b>", est["normal"]),
    ]]
    max_len = max(len(DOCS_PROPONENTE), len(DOCS_IMOVEL), len(DOCS_COOBRIGADOS))
    for i in range(max_len):
        c1 = f"[{'X' if chk.get('prop_' + DOCS_PROPONENTE[i]) else ' '}] {DOCS_PROPONENTE[i]}" if i < len(DOCS_PROPONENTE) else ""
        c2 = f"[{'X' if chk.get('imov_' + DOCS_IMOVEL[i]) else ' '}] {DOCS_IMOVEL[i]}" if i < len(DOCS_IMOVEL) else ""
        c3 = f"[{'X' if chk.get('coob_' + DOCS_COOBRIGADOS[i]) else ' '}] {DOCS_COOBRIGADOS[i]}" if i < len(DOCS_COOBRIGADOS) else ""
        linhas_chk.append([
            Paragraph(safe(c1), ParagraphStyle("Chk", parent=est["normal"], fontSize=7.5)),
            Paragraph(safe(c2), ParagraphStyle("Chk", parent=est["normal"], fontSize=7.5)),
            Paragraph(safe(c3), ParagraphStyle("Chk", parent=est["normal"], fontSize=7.5)),
        ])
    el.append(tabela_simples(linhas_chk, [7.2 * cm, 5.4 * cm, 5.4 * cm], est))
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        f"<b>Tipo de envio:</b> {safe(d.get('tipo_envio_docs'))} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Data envio docs:</b> {safe(d.get('data_envio_docs'))}",
        est["normal"],
    ))

    # Margem Crédito Pessoal e Avalistas
    el.append(Paragraph("MARGEM CRÉDITO PESSOAL / AVALISTAS", est["subtitulo"]))
    el.append(tabela_simples([
        [Paragraph(f"<b>Crédito:</b> {safe(d.get('credito_tipo'))} ({fmt_moeda(d.get('credito_valor'))})", est["normal"]),
         Paragraph(f"<b>Benefício:</b> {fmt_moeda(d.get('beneficio_valor'))}", est["normal"])],
        [Paragraph(f"<b>Parcela Consórcio:</b> {fmt_moeda(d.get('parcela_consorcio'))}", est["normal"]),
         Paragraph(f"<b>Nº Parcelas Consórcio:</b> {safe(d.get('num_parcelas_consorcio'))}", est["normal"])],
        [Paragraph(f"<b>Avalista:</b> {safe(d.get('avalista_nome'))} | CPF: {fmt_doc(d.get('avalista_cpf'))}", est["normal"]),
         Paragraph(f"<b>Cônjuge Aval.:</b> {safe(d.get('conjuge_avalista_nome'))} | CPF: {fmt_doc(d.get('conjuge_avalista_cpf'))}", est["normal"])],
    ], [9 * cm, 9 * cm], est))

    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), "Proponente"))
    return el


def doc_producao(d, est):
    el = bloco_cabecalho("ANÁLISE PRODUTIVA", est)
    el.append(tabela_simples([
        [Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>Enquadramento:</b> {safe(d.get('tipo_cliente'))}", est["normal"])],
        [Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"]),
         Paragraph(f"<b>Telefone:</b> {safe(d.get('cliente_telefone'))}", est["normal"])],
        [Paragraph(f"<b>Localidade:</b> {safe(d.get('localidade'))}", est["normal"]),
         Paragraph(f"<b>Município/UF:</b> {safe(d.get('cidade'))}/{safe(d.get('uf'))}", est["normal"])],
        [Paragraph(f"<b>Finalidade:</b> {safe(d.get('tipo_servico'))} - {safe(d.get('item_financiado'))}", est["normal"]),
         Paragraph(f"<b>Valor Proposto:</b> {fmt_moeda(d.get('valor_proposto'))}", est["normal"])],
    ], [10.5 * cm, 7.5 * cm], est))
    el.append(Spacer(1, 6))

    prod = d.get("dados_producao") or {}
    props = prod.get("propriedades") or []
    el.append(Paragraph("PROPRIEDADES E PRODUÇÃO AGRÍCOLA", est["subtitulo"]))

    if not props:
        el.append(Paragraph("Nenhuma propriedade produtiva detalhada nesta proposta.", est["normal"]))
    else:
        for idx, p in enumerate(props, start=1):
            rotulo = "Propriedade Beneficiada" if idx == 1 else f"Propriedade {idx}"
            el.append(tabela_simples([
                [Paragraph(f"<b>{rotulo}:</b> {safe(p.get('nome'))}", est["normal"]),
                 Paragraph(f"<b>Matrícula:</b> {safe(p.get('matricula'))}", est["normal"]),
                 Paragraph(f"<b>Nº Pés:</b> {safe(p.get('num_pes'))}", est["normal"])],
                [Paragraph(f"<b>Espaçamento:</b> {safe(p.get('espacamento'))}", est["normal"]),
                 Paragraph(f"<b>Variedades:</b> {safe(p.get('variedades'))}", est["normal"]),
                 Paragraph(f"<b>Idade:</b> {safe(p.get('idade'))}", est["normal"])],
                [Paragraph(f"<b>Prev. 2027:</b> {safe(p.get('prev_2027'))} | <b>Prod. 26/25/24:</b> {safe(p.get('prod_2026'))}/{safe(p.get('prod_2025'))}/{safe(p.get('prod_2024'))}", est["normal"]),
                 Paragraph(f"<b>Venda 2026:</b> {fmt_moeda(p.get('venda_2026'))}", est["normal"]),
                 Paragraph(f"<b>Venda 25/24:</b> {fmt_moeda(p.get('venda_2025'))} / {fmt_moeda(p.get('venda_2024'))}", est["normal"])],
            ], [7.2 * cm, 5.4 * cm, 5.4 * cm], est))
            el.append(Spacer(1, 4))

    sem = prod.get("semoventes") or {}
    el.append(Paragraph("SEMOVENTES, RENDA EXTRA E BENS", est["subtitulo"]))
    el.append(tabela_simples([
        [Paragraph(f"<b>Vacas de Leite:</b> {safe(sem.get('vacas_leite'))}", est["normal"]),
         Paragraph(f"<b>Litros/Dia:</b> {safe(sem.get('litros_dia'))}", est["normal"]),
         Paragraph(f"<b>Preço/Litro:</b> {fmt_moeda(sem.get('preco_litro'))}", est["normal"])],
        [Paragraph(f"<b>Boi de Corte:</b> {safe(sem.get('boi_corte'))}", est["normal"]),
         Paragraph(f"<b>Novilhas:</b> {safe(sem.get('novilhas'))}", est["normal"]),
         Paragraph(f"<b>Bezerros:</b> {safe(sem.get('bezerros'))}", est["normal"])],
        [Paragraph(f"<b>Renda Extra 1:</b> {safe(prod.get('renda_extra_1_desc'))} ({fmt_moeda(prod.get('renda_extra_1_val'))})", est["normal"]),
         Paragraph(f"<b>Renda Extra 2:</b> {safe(prod.get('renda_extra_2_desc'))} ({fmt_moeda(prod.get('renda_extra_2_val'))})", est["normal"]),
         Paragraph(f"<b>RENDA BRUTA ANUAL:</b> {fmt_moeda(d.get('renda_bruta_anual'))}", est["normal"])],
    ], [6 * cm, 6 * cm, 6 * cm], est))
    if prod.get("bens"):
        el.append(Spacer(1, 4))
        el.append(Paragraph(f"<b>Bens:</b> {safe(prod.get('bens'))}", est["normal"]))

    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), "Produtor Rural"))
    return el


def doc_ordem_servico(d, est):
    el = bloco_cabecalho("ORDEM DE SERVIÇO", est)
    el.append(tabela_simples([
        [Paragraph(f"<b>Local/Data:</b> {safe(d.get('local_emissao'))}, {fmt_data_br(d.get('data_proposta'))}", est["normal"]),
         Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"])],
        [Paragraph(f"<b>Cliente:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>Celular:</b> {safe(d.get('cliente_telefone'))}", est["normal"])],
        [Paragraph(f"<b>Endereço/Localidade:</b> {safe(d.get('localidade'))} - {safe(d.get('bairro'))}", est["normal"]),
         Paragraph(f"<b>Cidade/UF:</b> {safe(d.get('cidade'))}/{safe(d.get('uf'))}", est["normal"])],
    ], [10.5 * cm, 7.5 * cm], est))
    el.append(Spacer(1, 6))

    el.append(Paragraph("DESCRIÇÃO DO SERVIÇO CONTRATADO", est["subtitulo"]))
    el.append(tabela_simples([
        ["Item", "Descrição do Serviço", "Valor Operação"],
        ["1", Paragraph(f"<b>{safe(d.get('tipo_servico'))}</b> — Item: {safe(d.get('item_financiado'))}", est["normal"]), fmt_moeda(d.get("valor_proposto"))],
        ["2", Paragraph(safe(d.get("descricao_servico")), est["normal"]), "—"],
    ], [1.5 * cm, 12.5 * cm, 4 * cm], est, cabecalho_colorido=True))
    el.append(Spacer(1, 6))

    # Observações contratuais literais da planilha original
    obs = [
        "OBS. 1: O produtor terá que realizar o acerto (pagamento) da prestação dos serviços do ATER (escritório), na EMISSÃO DA MINUTA (contrato), onde já foram executados e finalizados os serviços do ATER (escritório).",
        "OBS. 2: Os serviços extras que são necessários executar no processo da operação de Crédito Rural assim solicitados pelo banco, terceiros e/ou próprio proponente, como: Licenças ou dispensas ambientais, CAR, Cartão de produtor, Contratos, Certidões e Levantamento Patrimonial (Pronamp BB), terão que realizar o ACERTO IMEDIATO, conforme a execução e entrega do documento pelo ATER (escritório).",
        "OBS. 3: Será cobrado do produtor o valor INTEGRAL dos serviços do ATER (escritório) conforme esta Ordem de Serviço. Em caso de desistência do produtor durante o processo de Crédito Rural, o pagamento será devido integralmente, visto que o serviço já foi executado.",
    ]
    for o in obs:
        el.append(Paragraph(safe(o), est["pequeno"]))
    el.append(Spacer(1, 6))

    # Resumo Financeiro da OS
    pct = float(d.get("percentual_honorario") or 0) * 100
    el.append(tabela_simples([
        ["Serviços Prestados", "Taxa Aplicada", "Subtotal", "Desconto", "Acréscimos", "TOTAL"],
        [
            "PROJETO TÉCNICO",
            f"{pct:.2f}%",
            fmt_moeda(d.get("valor_projeto_tecnico")),
            fmt_moeda(d.get("desconto")),
            fmt_moeda(d.get("acrescimos")),
            fmt_moeda(d.get("valor_total_os")),
        ],
    ], [4.5 * cm, 2.3 * cm, 2.8 * cm, 2.7 * cm, 2.7 * cm, 3 * cm], est, cabecalho_colorido=True))
    el.append(Spacer(1, 5))
    el.append(Paragraph(
        f"<b>Forma de Pagamento:</b> {safe(d.get('forma_pagamento'))} &nbsp;|&nbsp; "
        f"<b>Parcelamento:</b> {int(d.get('num_parcelas') or 1)}x de {fmt_moeda(d.get('valor_parcela'))}",
        est["normal"],
    ))
    el.append(Spacer(1, 4))
    el.append(Paragraph("Autorizo os serviços, as taxas e os valores acima descritos.", est["normal"]))

    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), "Contratante / Produtor Rural"))
    el.append(Spacer(1, 12))
    el.append(Paragraph("____________________________________________________________", est["centro"]))
    el.append(Paragraph(f"<b>{safe(EMPRESA['razao_social'].upper())}</b>", est["centro"]))
    el.append(Spacer(1, 10))
    el.append(Paragraph(
        "<b>Comprovante de Recebimento dos Serviços:</b> Confirmo que o serviço foi prestado de acordo com o combinado. "
        "Data de entrega: ____/____/______  Assinatura: ____________________________",
        est["pequeno"],
    ))
    return el


def doc_protecao_dados(d, est):
    el = bloco_cabecalho("TERMO DE CONSENTIMENTO PARA USO DE DADOS PESSOAIS E IMAGEM (LGPD)", est)
    p1 = (
        f"Pelo presente termo, autorizo a {EMPRESA['razao_social']}, CNPJ nº {EMPRESA['cnpj']}, "
        f"com sede na {EMPRESA['endereco_completo']}, telefones {EMPRESA['telefones']} e e-mail {EMPRESA['email']}, "
        "a tratar os dados pessoais e documentos fornecidos por mim ou obtidos junto ao escritório de contabilidade "
        "por mim indicado, exclusivamente para prestar os serviços solicitados: assessoria rural, organização e "
        "instrução de propostas de crédito rural, imobiliário ou comercial, regularização de imóveis e atividades relacionadas."
    )
    el.append(Paragraph(safe(p1), est["justificado"]))
    el.append(tabela_simples([
        [Paragraph(f"<b>Contabilidade Indicada:</b> {safe(d.get('contabilidade_nome'))}", est["normal"]),
         Paragraph(f"<b>CNPJ Contabilidade:</b> {safe(d.get('contabilidade_cnpj'))}", est["normal"])],
        [Paragraph(f"<b>Instituição Financeira:</b> {safe(d.get('banco_destino'))}", est["normal"]),
         Paragraph("<b>Abrangência:</b> Instituições financeiras e cooperativas", est["normal"])],
    ], [9.5 * cm, 8.5 * cm], est))
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
    el.append(Paragraph("[  ] Li e aceito o tratamento dos meus dados para as finalidades descritas neste termo.", est["normal"]))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), "Titular dos Dados"))
    return el


def doc_galpao_graos(d, est):
    el = bloco_cabecalho("DECLARAÇÃO — GALPÃO PARA ARMAZENAGEM DE GRÃOS", est)
    el.append(tabela_simples([
        [Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"])],
    ], [11.5 * cm, 6.5 * cm], est))
    el.append(Spacer(1, 8))
    paragrafos = [
        "(1) O investimento solicitado será destinado à construção de um galpão de armazenagem de grãos.",
        "(2) A área destinada à armazenagem terá como finalidade única a guarda e conservação dos grãos, não sendo utilizada para beneficiamento, industrialização ou qualquer outro fim.",
        "(3) Comprometo-me a utilizar os recursos conforme informado, estando ciente de que qualquer destinação diversa poderá implicar em responsabilização civil, administrativa e/ou criminal, conforme a legislação vigente.",
        "(4) Declaro estar ciente de que a execução da obra será realizada sob minha total responsabilidade, incluindo a contratação de mão de obra, aquisição de materiais e observância das normas técnicas e legais aplicáveis, isentando a assessoria ou qualquer instituição financeira de qualquer responsabilidade relativa à execução da construção/reforma.",
        "Declaro ainda estar ciente de que a veracidade das informações aqui prestadas é de minha inteira responsabilidade.",
    ]
    for p in paragrafos:
        el.append(Paragraph(safe(p), est["justificado"]))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_autorizacao_compartilhamento(d, est, banco_nome, parceira_txt):
    """Modelo padrão das 5 abas AUTORIZAÇÃO (SICOOB, BB, BRADESCO, CRESOL, CAIXA)."""
    el = bloco_cabecalho(f"AUTORIZAÇÃO PARA COMPARTILHAMENTO — {banco_nome.upper()}", est, "Agronegócios")
    el.append(tabela_simples([
        [Paragraph(f"<b>Proponente:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"])],
    ], [11.5 * cm, 6.5 * cm], est))
    el.append(Spacer(1, 10))
    el.append(Paragraph("DECLARAÇÃO", est["subtitulo"]))
    t1 = (
        f"Autorizo {parceira_txt} a fornecer à empresa {EMPRESA['razao_social'].upper()}, CNPJ: {EMPRESA['cnpj']}, "
        f"parceira no acolhimento de proposta de Agronegócios, as informações registradas em meu cadastro relativas "
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
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_sicoob_bndes(d, est):
    el = bloco_cabecalho("PROPOSTA PARA OS PROGRAMAS DO BNDES", est, f"SICOOB — Singular: {EMPRESA['sicoob_singular']}")
    el.append(tabela_simples([
        [Paragraph(f"<b>Nome do Cooperado:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"])],
    ], [11.5 * cm, 6.5 * cm], est))
    el.append(Spacer(1, 6))
    el.append(Paragraph("DECLARAÇÃO E AUTORIZAÇÃO DO PROPONENTE:", est["subtitulo"]))
    textos = [
        "Declaração da autorização para consulta ao Sistema de Operações do Crédito Rural Sicor: Quando se tratar de operação de Crédito Rural, autorizo o Credor a: (i) consultar o Sistema de Operações do Crédito Rural e do Proagro (Sicor), gerido pelo Banco Central do Brasil, para a obtenção de dados e informações cadastrais, necessários à análise e concessão do crédito e enquadramento de garantias, autorização essa estendida, desde já, às demais instituições que podem consultar o Sicor nos termos da regulamentação vigente; e (ii) ter acesso aos dados registrados no Sicor sobre operações ativas e passivas e serviços prestados por instituições financeiras, bem como demais informações pessoais que serão exibidos por tais consultas pelo CREDOR. Declaro ciência, desde já, que o Sicor se destina ao registro das operações de crédito rural concedidas pelas instituições financeiras autorizadas a operar em crédito rural, bem como dos enquadramentos de empreendimentos no Programa de Garantia da Atividade Agropecuária (Proagro).",
        "Declaração do mutuário para operações de PRONAMP ou Moderfrota PRONAMP: Declaro ao Sicoob ter, no mínimo, 80% (oitenta por cento) da renda bruta anual originária da atividade agropecuária.",
        "Declaração do mutuário para os casos em que houver previsão de redução do quadro de pessoal em operações do Programa Fundo Clima: Declaro ao Sicoob que, para os casos em que houver previsão de redução do quadro de pessoal, estou ciente da recomendação para a implementação de programas de qualificação e requalificação profissional, focados preferencialmente nos princípios de transição justa e de políticas inclusivas com envolvimento das entidades comunitárias locais.",
        "Declaração de inexistência de impedimento para realização de transações com o Sistema BNDES: Declaro ao Sicoob que não possuo impedimentos à realização de transações com o Sistema BNDES. Isto é, não estou listado(a) entre as pessoas e entidades identificadas no item 'Vedações e Limites' da Política para Transações com Partes Relacionadas do Sistema BNDES.",
        "Declaração do mutuário sobre a existência de operações de Pronaf Investimento: Declaro ao Sicoob que, em caso de possuir operação(ões) contratada(s) de PRONAF investimento em qualquer instituição financeira integrante do Sistema Nacional de Crédito Rural - SNCR, eu as discriminarei na tabela abaixo. Para efeito desta declaração estou considerando operação(ões) individual(is) e participação(ões) em crédito(s) grupal(is) ou coletivo(s), para apuração do limite de endividamento desta linha de crédito. Reconheço que declaração falsa implica na desclassificação da operação de crédito rural, além das demais sanções e penalidades previstas em lei e no Manual de Crédito Rural - MCR do Banco Central do Brasil.",
    ]
    for t in textos:
        el.append(Paragraph(safe(t), est["pequeno"]))
    el.append(Spacer(1, 5))
    el.append(tabela_simples([
        ["Programa", "Finalidade", "Contratação", "Vencimento", "Valor"],
        [safe(d.get("tipo_servico")), safe(d.get("item_financiado")), "", "", fmt_moeda(d.get("valor_proposto"))],
    ], [4.5 * cm, 4.5 * cm, 3 * cm, 3 * cm, 3 * cm], est, cabecalho_colorido=True))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_consulta_bacen_cooperativa(d, est, cooperativa_nome):
    """Usado nas abas SICOOB e CRESOL (Consulta BACEN + SERASA/SPC)."""
    el = bloco_cabecalho("AUTORIZAÇÃO PARA CONSULTA AO BANCO CENTRAL", est, cooperativa_nome)
    el.append(tabela_simples([
        [Paragraph(f"<b>Nome:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"])],
    ], [11.5 * cm, 6.5 * cm], est))
    el.append(Spacer(1, 10))
    ps = [
        f"Autorizamos o {cooperativa_nome} a consultar as informações consolidadas, relativas a nossos nomes e da empresa em que somos sócios, constantes do Sistema Central de Risco de Crédito do BACEN.",
        f"Autorizamos, ainda, o {cooperativa_nome} a fornecer informações sobre as operações de crédito com ela realizadas, no sentido de compor o cadastro do já citado Sistema.",
        "Os presentes dados são verdadeiros e visam facilitar os processos de negociação e transações comerciais, pela antecipação de informações a nosso respeito.",
        "Autorizamos o arquivamento dos nossos dados pessoais e de idoneidade na SERASA – Centralização de Serviços dos Bancos S/A e/ou SPC/CDL – Serviço de Proteção ao Crédito, que poderá deles se utilizar, respeitadas as disposições legais em vigor.",
    ]
    for p in ps:
        el.append(Paragraph(safe(p), est["justificado"]))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_termo_sicoob(d, est):
    el = bloco_cabecalho("TERMO DE AUTORIZAÇÃO PARA CONSULTA DOS DADOS NO SICOR / PROAGRO", est, "SICOOB")
    t1 = (
        f"Através do presente instrumento, eu <b>{safe(d.get('cliente_nome'))}</b>, inscrito(a) no CPF/CNPJ sob nº "
        f"<b>{fmt_doc(d.get('cliente_cpf'))}</b>, autorizo a cooperativa de crédito de meu relacionamento a consultar o "
        "Sistema de Operações do Crédito Rural e do Proagro (Sicor), gerido pelo Banco Central do Brasil, para a obtenção "
        "de dados e informações pessoais/cadastrais, necessários à análise de concessão do crédito e enquadramento de garantias, "
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
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_bb_scr(d, est, nome_assinante, cpf_assinante, rotulo):
    """Usado nas abas B. DO BRASIL, BB AVAL e BB CONJUGE AVAL."""
    el = bloco_cabecalho("AUTORIZAÇÃO PARA COMPARTILHAMENTO DE DADOS CADASTRAIS E CONSULTA AO SCR", est, f"BANCO DO BRASIL ({rotulo})")
    ps = [
        f"Autorizo o Banco do Brasil S.A. a fornecer às empresas {EMPRESA['razao_social']}, CNPJ: {EMPRESA['cnpj']} e Cobra Tecnologia S/A, CNPJ 42.318.949/0001-84, parceiras do Banco do Brasil S.A. no acolhimento e análise de proposta, informações registradas em meu cadastro relativas aos meus dados pessoais, profissionais e residenciais, bem como referentes a imóveis urbanos ou rurais de minha propriedade, sem menção a valor econômico.",
        "As informações, cujo fornecimento é autorizado, deverão ser utilizadas exclusivamente para fins de instruir a minha proposta de crédito junto ao Banco do Brasil S.A., não podendo contemplar informação de saldo de operações ativas ou passivas de minha responsabilidade.",
        "Autorizo, ainda, o conglomerado Banco do Brasil S.A. a consultar os débitos e responsabilidades decorrentes de operações com características de crédito e as informações e os registros de medidas judiciais que em meu nome constem ou venham a constar do Sistema de Informações de Crédito (SCR), gerido pelo Banco Central do Brasil - Bacen, ou dos sistemas que venham a complementá-lo ou a substituí-lo.",
        "Estou ciente de que: a) o SCR tem por finalidades fornecer informações ao Bacen para fins de supervisão do risco de crédito e propiciar o intercâmbio de informações entre instituições financeiras; b) poderei ter acesso aos dados constantes em meu nome no SCR por meio da Central de Atendimento ao Público do Banco Central do Brasil (CAP); c) pedidos de correções, de exclusões e de manifestações de discordância quanto às informações constantes do SCR deverão ser dirigidas ao Bacen ou à instituição responsável pela remessa das informações; d) a consulta sobre qualquer informação ao SCR depende de minha prévia autorização; e) mais informações podem ser obtidas em www.bcb.gov.br ou www.bb.com.br.",
    ]
    for p in ps:
        el.append(Paragraph(safe(p), est["pequeno"]))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), nome_assinante, cpf_assinante, rotulo))
    el.append(Spacer(1, 10))
    el.append(Paragraph(
        "Telefones BB: Central de Atendimento 4004-0001 / 0800-729-0001 | SAC 0800-729-0722 | Deficientes Auditivos/Fala 0800-729-0088 | Ouvidoria BB 0800-729-5678.",
        ParagraphStyle("RodBB", parent=est["pequeno"], fontSize=7, textColor=colors.grey),
    ))
    return el


def doc_sicor(d, est, nome_assinante, cpf_assinante, rotulo):
    """Usado nas abas SICOR, SICOR AVAL e SICOR CONJUGE AVAL."""
    el = bloco_cabecalho("AUTORIZAÇÃO PARA CONSULTA AO SICOR", est, f"BANCO DO BRASIL ({rotulo})")
    el.append(Paragraph(
        "Autorizo(amos) o conglomerado Banco do Brasil S.A. (BB) a consultar o Sistema de Operações de Crédito Rural e do Proagro (SICOR), "
        "gerido pelo Bacen, a respeito de informações referentes a operações de crédito rural e Proagro que eu(nós) possuo(ímos) junto a "
        "qualquer instituição financeira integrante do Sistema Nacional de Crédito Rural (SNCR). Estou(amos) ciente(s) de que:",
        est["pequeno"],
    ))
    alineas = [
        "a) o SICOR tem por finalidade prover o Bacen de informações sobre dados de crédito rural e operações enquadradas no Proagro para fins de monitoramento e fiscalização, nos termos do Manual de Crédito Rural, bem como propiciar o intercâmbio de informações entre instituições financeiras definidas no §1º do artigo 1º da Lei Complementar nº 105/2001;",
        "b) a consulta sobre qualquer informação registrada no SICOR depende de minha(nossa) prévia autorização;",
        "c) poderei(emos) ter acesso aos dados constantes em meu(nosso) nome no SICOR por meio do sistema Registrato do Bacen;",
        "d) pedidos de correções, exclusões e manifestações de discordância quanto às informações constantes do SICOR deverão ser dirigidos ao BB, por meio de requerimento escrito e fundamentado, ou pela respectiva decisão judicial, quando o BB tiver sido o responsável pelo envio;",
        "e) o Conglomerado Banco do Brasil é obrigado a enviar para registro no SICOR/Bacen as informações sobre operações de crédito rural e Proagro contratadas e a serem contratadas por mim(nós);",
        "f) mais informações sobre o SICOR podem ser obtidas em www.bcb.gov.br ou www.bb.com.br.",
    ]
    for a in alineas:
        el.append(Paragraph(safe(a), est["pequeno"]))
    el.append(Paragraph(
        "Por fim, declaro(amos) ciente(s) de que a consulta supracitada, por implicar tratamento de meus(nossos) dados pessoais, "
        "ocorrerá em conformidade com a Lei nº 13.709/2018 (LGPD) e demais normas aplicáveis, visando procedimentos preliminares "
        "relacionados a eventual contratação solicitada e cumprimento de obrigações legais ou regulatórias.",
        est["pequeno"],
    ))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), nome_assinante, cpf_assinante, rotulo))
    return el


def doc_bradesco(d, est):
    el = bloco_cabecalho("AUTORIZAÇÃO PARA CONSULTA AO SICOR — BANCO BRADESCO S/A", est)
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
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_caixa(d, est):
    el = bloco_cabecalho("AUTORIZAÇÃO DE CONSULTA AO SCR E SICOR — CAIXA ECONÔMICA FEDERAL", est)
    el.append(tabela_simples([
        [Paragraph(f"<b>Nome Completo:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"])],
    ], [11.5 * cm, 6.5 * cm], est))
    el.append(Spacer(1, 10))
    el.append(Paragraph(
        "Declaro que AUTORIZO, nos termos da Resolução CMN nº 3.658, de 17/12/2008, a CAIXA ECONÔMICA FEDERAL "
        "a consultar as informações consolidadas relativas à minha pessoa, constantes no Sistema de Informações de "
        "Créditos (SCR) e no Sistema de Operações do Crédito Rural e do Proagro (Sicor), ambos do BACEN.",
        est["justificado"],
    ))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf")))
    return el


def doc_invest_caixa(d, est):
    el = bloco_cabecalho("DECLARAÇÃO DE RENEGOCIAÇÕES POR RESOLUÇÕES DO CMN", est, "CAIXA ECONÔMICA FEDERAL — Grau de Sigilo #00")
    el.append(tabela_simples([
        [Paragraph(f"<b>Cód. Agência:</b> {safe(EMPRESA['caixa_cod_agencia'])}", est["normal"]),
         Paragraph(f"<b>Nome da Agência:</b> {safe(EMPRESA['caixa_nome_agencia'])}", est["normal"])],
        [Paragraph(f"<b>Nome/Razão Social:</b> {safe(d.get('cliente_nome'))}", est["normal"]),
         Paragraph(f"<b>CPF/CNPJ:</b> {fmt_doc(d.get('cliente_cpf'))}", est["normal"])],
    ], [9 * cm, 9 * cm], est))
    el.append(Spacer(1, 6))
    el.append(Paragraph("[  ] Declaro, sob as penas da lei, que NÃO POSSUO operação(ões) de Crédito Rural ativa(s) renegociada(s) com base nas Resoluções do CMN descritas abaixo.", est["pequeno"]))
    el.append(Paragraph("[  ] Declaro, sob as penas da lei, que POSSUO operação(ões) de Crédito Rural ativa(s) renegociada(s) com base nas Resoluções do CMN descritas abaixo:", est["pequeno"]))
    el.append(Spacer(1, 4))

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
        [Paragraph(f"<b>{safe(r)}</b>", est["pequeno"]), Paragraph(safe(desc), est["pequeno"])]
        for r, desc in resolucoes
    ]
    el.append(tabela_simples(linhas_res, [5 * cm, 13 * cm], est, cabecalho_colorido=True))
    el.append(Spacer(1, 5))
    el.append(Paragraph(
        "Estou(amos) ciente(s) de que declaração falsa implica substituição, desde a data da contratação, da taxa de juros "
        "pactuada por taxa de mercado, sem prejuízo das demais sanções e penalidades previstas em lei e no Manual de Crédito Rural – MCR.",
        est["pequeno"],
    ))
    el.extend(bloco_assinatura(est, d.get("local_emissao"), d.get("data_proposta"), d.get("cliente_nome"), d.get("cliente_cpf"), "Cliente ou Representante Legal"))
    return el


# ============================================================================
# ROTEADOR CENTRAL: MONTA 1 DOCUMENTO OU UM PACOTE COMPLETO EM UM ÚNICO PDF
# ============================================================================
def gerar_pdf_bytes(dados_proposta, lista_documentos):
    """
    Recebe um dicionário com os dados da proposta e uma lista de nomes de
    documentos (ex: ['NOVA PROPOSTA', 'ORDEM DE SERVIÇO', 'B. DO BRASIL']).
    Devolve os bytes prontos de um único PDF contendo todas as páginas.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        title="Pacote Carta-Proposta - Regularize",
    )
    est = criar_estilos()
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

    doc.build(story)
    return buffer.getvalue()
