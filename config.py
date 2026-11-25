# ============================================================================
# ARQUIVO: config.py
# O QUE ESTE ARQUIVO FAZ:
#   Centraliza TODAS as configurações da sua empresa e regras do sistema.
#   Se um dia você mudar de endereço, telefone, cidade ou taxa da Ordem de
#   Serviço, basta alterar aqui — NÃO precisa mexer no resto do código!
# ============================================================================

# ============================================================================
# >>> CONFIGURE AQUI: DADOS DA SUA EMPRESA (APARECEM NOS DOCUMENTOS E PDFs) <<<
# ============================================================================
EMPRESA = {
    "nome_fantasia": "Regularize Assessoria Rural",
    "razao_social": "Regularize Assessoria Rural Ltda.",
    "cnpj": "32.916.668/0001-70",
    "endereco_completo": "Rua Marinho Carlos de Souza, 199, loja 1, Centro, Divino/MG",
    "telefones": "(32) 99911-6790 / 99970-1414",
    "email": "regularizeassessoriarural@gmail.com",
    "cidade_padrao": "Divino",
    "uf_padrao": "MG",
    # Códigos usados nos formulários específicos do Sicoob e da Caixa:
    "sicoob_singular": "3118",
    "sicoob_cooperativa": "SICOOB CREDISUDESTE",
    "cresol_cooperativa": "CRESOL ZONA DA MATA",
    "caixa_cod_agencia": "4401",
    "caixa_nome_agencia": "Divino",
}

# ============================================================================
# >>> CONFIGURE AQUI: FAIXAS DE HONORÁRIOS DA ORDEM DE SERVIÇO <<<
# Replica exatamente a fórmula CHOOSE('NOVA PROPOSTA'!$XFB$1, 0, 0.02, ...)
# ============================================================================
FAIXAS_HONORARIOS = {
    1: {"rotulo": "Isento (0,00%)", "percentual": 0.0000},
    2: {"rotulo": "Faixa Padrão (2,00%)", "percentual": 0.0200},
    3: {"rotulo": "Desconto 1 (1,80%)", "percentual": 0.0180},
    4: {"rotulo": "Desconto 2 (1,50%)", "percentual": 0.0150},
    5: {"rotulo": "Desconto 3 (1,25%)", "percentual": 0.0125},
    6: {"rotulo": "Desconto 4 (1,00%)", "percentual": 0.0100},
}

# ============================================================================
# >>> CONFIGURE AQUI: CHECKLIST DE DOCUMENTOS DA CARTA-PROPOSTA <<<
# Mesmos itens da aba NOVA PROPOSTA (linhas 30 a 40)
# ============================================================================
DOCS_PROPONENTE = [
    "Identidade ou CNH",
    "Comp. de endereço (atual)",
    "Cartão do Produtor",
    "IRPF",
    "Guias (NF da Cultura)",
    "Orçamento do bem",
    "CAF/DAP (Pronaf)",
    "Cert. Casamento",
    "Identidade/CNH Cônjuge",
    "Contrato (Arrendamento, Parceria ou Comodato)",
]

DOCS_IMOVEL = [
    "CAR",
    "ITR",
    "CCIR",
    "Certidão de Inteiro Teor (atual)",
]

DOCS_COOBRIGADOS = [
    "Identidade ou CNH",
    "Identidade/CNH Cônjuge",
    "Certidão de Casamento",
    "Comp. Endereço (atual)",
]

# ============================================================================
# >>> CONFIGURE AQUI: PACOTES DE DOCUMENTOS POR BANCO <<<
# Define quais documentos entram automaticamente em cada Pacote PDF.
# ============================================================================
DOCUMENTOS_CLIENTE_PADRAO = [
    "NOVA PROPOSTA",
    "PRODUÇÃO",
    "ORDEM DE SERVIÇO",
    "PROTEÇÃO DE DADOS",
]

PACOTES_BANCOS = {
    "PACOTE CLIENTE (SEM BANCO)": [],
    "SICOOB": [
        "SICOOB BNDES",
        "AUTORIZAÇÃO SICOOB",
        "SICOOB",
        "TERMO SICOOB",
    ],
    "BANCO DO BRASIL": [
        "B. DO BRASIL",
        "AUTORIZAÇÃO BB",
        "SICOR",
        # Nota: BB AVAL, BB CONJUGE AVAL, SICOR AVAL e SICOR CONJUGE AVAL
        # são incluídos automaticamente se houver Avalista/Cônjuge preenchido!
    ],
    "BRADESCO": [
        "BRADESCO",
        "AUTORIZAÇÃO BRADESCO",
    ],
    "CRESOL": [
        "CRESOL",
        "AUTORIZAÇÃO CRESOL",
    ],
    "CAIXA": [
        "CAIXA",
        "AUTORIZAÇÃO CAIXA",
        "INVEST CAIXA",
    ],
}

TODOS_OS_DOCUMENTOS = [
    "NOVA PROPOSTA",
    "PRODUÇÃO",
    "ORDEM DE SERVIÇO",
    "PROTEÇÃO DE DADOS",
    "GALPÃO DE GRÃOS",
    "SICOOB BNDES",
    "AUTORIZAÇÃO SICOOB",
    "SICOOB",
    "TERMO SICOOB",
    "B. DO BRASIL",
    "AUTORIZAÇÃO BB",
    "BB AVAL",
    "BB CONJUGE AVAL",
    "SICOR",
    "SICOR AVAL",
    "SICOR CONJUGE AVAL",
    "BRADESCO",
    "AUTORIZAÇÃO BRADESCO",
    "CRESOL",
    "AUTORIZAÇÃO CRESOL",
    "CAIXA",
    "AUTORIZAÇÃO CAIXA",
    "INVEST CAIXA",
]
