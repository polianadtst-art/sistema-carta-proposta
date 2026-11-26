# ============================================================================
# ARQUIVO: config.py (Versão 12.0 — Regularize Assessoria Rural)
# O QUE ESTE ARQUIVO FAZ:
#   Centraliza TODAS as configurações da Regularize Assessoria Rural com
#   todas as listas selecionáveis organizadas em ORDEM ALFABÉTICA (A–Z, PT-BR):
#   - Dados da empresa (CNPJ, endereço, telefones, agência)
#   - Faixas de honorários e descontos da Ordem de Serviço
#   - Carências (Não, SIM 1 ano, 2 anos e 3 anos)
#   - Principais culturas de Minas Gerais (A–Z)
#   - Linhas de crédito, itens financiáveis por linha e descrições completas (A–Z)
#   - Municípios de bancos/cooperativas num raio de 150 km de Divino - MG (A–Z)
#   - Administradores Master e perfis de autorização (A–Z)
# ============================================================================

# ============================================================================
# 1. DADOS DA EMPRESA (APARECEM NOS DOCUMENTOS E PDFs IMPRESSOS)
# ============================================================================
EMPRESA = {
    'nome_fantasia': 'Regularize Assessoria Rural',
    'razao_social': 'Regularize Assessoria Rural Ltda.',
    'cnpj': '32.916.668/0001-70',
    'endereco_completo': 'Rua Marinho Carlos de Souza, 199, loja 1, Centro, Divino/MG',
    'telefones': '(32) 99911-6790 / 99970-1414',
    'email': 'regularizeassessoriarural@gmail.com',
    'cidade_padrao': 'Divino',
    'uf_padrao': 'MG',
    'sicoob_singular': '3118',
    'sicoob_cooperativa': 'SICOOB CREDISUDESTE',
    'cresol_cooperativa': 'CRESOL ZONA DA MATA',
    'caixa_cod_agencia': '4401',
    'caixa_nome_agencia': 'Divino',
}

# ============================================================================
# 2. FAIXAS DE HONORÁRIOS DA ORDEM DE SERVIÇO (ORDEM ALFABÉTICA)
# ============================================================================
TAXA_HONORARIO_CHEIA = 0.02  # 2,00% (valor cheio padrão)

FAIXAS_HONORARIOS = {
    3: {'rotulo': 'Desconto de 0,20% — Taxa final 1,80%', 'percentual': 0.018, 'desconto_pct': 0.002},
    4: {'rotulo': 'Desconto de 0,50% — Taxa final 1,50%', 'percentual': 0.015, 'desconto_pct': 0.005},
    5: {'rotulo': 'Desconto de 0,75% — Taxa final 1,25%', 'percentual': 0.0125, 'desconto_pct': 0.0075},
    6: {'rotulo': 'Desconto de 1,00% — Taxa final 1,00%', 'percentual': 0.01, 'desconto_pct': 0.01},
    1: {'rotulo': 'Isento — Desconto de 2,00% (Taxa final 0,00%)', 'percentual': 0.0, 'desconto_pct': 0.02},
    2: {'rotulo': 'Sem desconto — 2,00% (Valor Cheio)', 'percentual': 0.02, 'desconto_pct': 0.0},
}

# ============================================================================
# 3. OPÇÕES DE CARÊNCIA (ORDEM ALFABÉTICA)
# ============================================================================
CARENCIAS_PADRAO = [
    'Não',
    'SIM (1 ano)',
    'SIM (2 anos)',
    'SIM (3 anos)',
]

# ============================================================================
# 4. PRINCIPAIS CULTURAS E ATIVIDADES DE MINAS GERAIS (ORDEM ALFABÉTICA A–Z)
# ============================================================================
CULTURAS_MG = [
    'ABACATE',
    'ALHO',
    'APICULTURA',
    'AVICULTURA',
    'BANANA',
    'BATATA',
    'CAFÉ ARÁBICA',
    'CAFÉ CONILON',
    'CANA-DE-AÇÚCAR',
    'CEBOLA',
    'CENOURA',
    'EUCALIPTO / SILVICULTURA',
    'FEIJÃO',
    'HORTIFRUTIGRANJEIRO (OLERICULTURA)',
    'LARANJA / CITROS',
    'MANDIOCA',
    'MANGA',
    'MARACUJÁ',
    'MILHO (GRÃO / SILAGEM)',
    'MORANGO',
    'OVINOCAPRINOCULTURA',
    'PASTAGEM / FORRAGEIRAS',
    'PECUÁRIA DE CORTE',
    'PECUÁRIA LEITEIRA',
    'PISCICULTURA',
    'SOJA',
    'SORGO',
    'SUINOCULTURA',
    'TOMATE',
    'TRIGO',
    'UVA',
    'OUTRA CULTURA / ATIVIDADE',
]

# ============================================================================
# 5. LINHAS DE CRÉDITO, ITENS FINANCIÁVEIS E DESCRIÇÕES (ORDEM ALFABÉTICA A–Z)
# ============================================================================
CATALOGO_SERVICOS = {
    'CAR - CADASTRO AMBIENTAL RURAL': {
        'linha': 'REGULARIZAÇÃO',
        'descricao': 'Serviço de Regularização Ambiental — CAR: Orientação técnica, conferência de perímetros/matrículas e apoio completo na inscrição, retificação ou regularização do Cadastro Ambiental Rural (CAR) do imóvel, com base nos dados e documentos fornecidos pelo produtor.',
        'itens': [
            'INSCRIÇÃO DE CAR',
            'REGULARIZAÇÃO AMBIENTAL (PRA / RESERVA LEGAL)',
            'RETIFICAÇÃO / ATUALIZAÇÃO DE CAR',
        ],
    },
    'CARTÃO DE PRODUTOR': {
        'linha': 'REGULARIZAÇÃO',
        'descricao': 'Serviço de Regularização Cadastral — Cartão de Produtor Rural: Apoio técnico na solicitação, renovação ou regularização do Cartão de Produtor Rural, incluindo conferência das informações cadastrais e organização dos documentos exigidos pelo órgão competente.',
        'itens': [
            'EMISSÃO DE CARTÃO DE PRODUTOR RURAL',
            'RENOVAÇÃO / ATUALIZAÇÃO DE CARTÃO DE PRODUTOR',
        ],
    },
    'CONSÓRCIO': {
        'linha': 'CONSÓRCIO',
        'descricao': 'Linha Consórcio Rural — Serviço de Estruturação de Proposta: Análise cadastral, simulação e organização das informações e documentos da operação vinculada a consórcio de máquinas, veículos, imóveis ou equipamentos, com encaminhamento da proposta à instituição responsável.',
        'itens': [
            'CONSÓRCIO DE CAMINHONETE / VEÍCULO',
            'CONSÓRCIO DE ENERGIA SOLAR / EQUIPAMENTOS',
            'CONSÓRCIO DE IMÓVEL RURAL / GALPÃO',
            'CONSÓRCIO DE TRATOR / MÁQUINA AGRÍCOLA',
        ],
    },
    'CONTRATO - ARRENDATÁRIO': {
        'linha': 'CONTRATOS RURAIS',
        'descricao': 'Serviço de Contratos Rurais — Arrendamento Rural: Elaboração e organização de instrumento contratual de arrendamento rural, com qualificação das partes, identificação da área/matrícula, prazo, cultura e condições acordadas entre os envolvidos para fins de crédito rural.',
        'itens': [
            'ADITIVO / RENOVAÇÃO DE CONTRATO DE ARRENDAMENTO',
            'ELABORAÇÃO DE CONTRATO DE ARRENDAMENTO RURAL',
        ],
    },
    'CONTRATO - COMODATÁRIO': {
        'linha': 'CONTRATOS RURAIS',
        'descricao': 'Serviço de Contratos Rurais — Comodato Rural: Elaboração e organização de contrato de comodato rural, com qualificação completa das partes, identificação do imóvel e condições de cessão gratuita informadas pelos envolvidos para instrução bancária.',
        'itens': [
            'ADITIVO / RENOVAÇÃO DE CONTRATO DE COMODATO',
            'ELABORAÇÃO DE CONTRATO DE COMODATO RURAL',
        ],
    },
    'CONTRATO - PARCERIA': {
        'linha': 'CONTRATOS RURAIS',
        'descricao': 'Serviço de Contratos Rurais — Parceria Rural: Elaboração e organização de contrato de parceria agrícola ou pecuária, com qualificação das partes, identificação do imóvel, percentual de partilha e demais condições informadas pelos envolvidos.',
        'itens': [
            'ELABORAÇÃO DE CONTRATO DE PARCERIA AGRÍCOLA',
            'ELABORAÇÃO DE CONTRATO DE PARCERIA PECUÁRIA',
        ],
    },
    'CONTRATO - POSSEIRO': {
        'linha': 'CONTRATOS RURAIS',
        'descricao': 'Serviço de Contratos Rurais — Posse / Cessão de Uso: Organização de instrumento contratual e declaração relacionada à posse e ao uso produtivo do imóvel rural, conforme documentos e condições informados pelas partes para instrução cadastral.',
        'itens': [
            'CONTRATO / DECLARAÇÃO DE POSSE RURAL',
            'TERMO DE CESSÃO DE USO DE IMÓVEL RURAL',
        ],
    },
    'CRÉDITO RURAL GERAL - CUSTEIO': {
        'linha': 'CRÉDITO RURAL GERAL',
        'descricao': 'Linha Crédito Rural Geral (Demais Produtores) — Serviço de Custeio: Elaboração técnica, levantamento produtivo e instrução de proposta de custeio agrícola ou pecuário com recursos obrigatórios ou livres, com conferência completa dos documentos e protocolo junto à instituição financeira.',
        'itens': [
            'CUSTEIO AGRÍCOLA (ADUBOS, DEFENSIVOS E COLHEITA)',
            'CUSTEIO DE BENEFICIAMENTO DE SAFRA',
            'CUSTEIO PECUÁRIO (RAÇÃO, SANIDADE E PASTAGEM)',
        ],
    },
    'CRÉDITO RURAL GERAL - INVESTIMENTO': {
        'linha': 'CRÉDITO RURAL GERAL',
        'descricao': 'Linha Crédito Rural Geral (Demais Produtores) — Serviço de Investimento: Elaboração de projeto técnico e instrução documental de proposta de investimento rural com recursos controlados ou livres para aquisição de máquinas, benfeitorias, irrigação, energia solar ou implantação de lavouras.',
        'itens': [
            'AQUISIÇÃO DE MATRIZES E ANIMAIS',
            'FORMAÇÃO / RENOVAÇÃO DE LAVOURAS',
            'INFRAESTRUTURA RURAL / GALPÃO / TERREIRO',
            'IRRIGAÇÃO E ENERGIA SOLAR',
            'MÁQUINAS E EQUIPAMENTOS AGRÍCOLAS',
        ],
    },
    'PRONAF - CUSTEIO AGRÍCOLA': {
        'linha': 'PRONAF',
        'descricao': 'Linha PRONAF — Serviço de Custeio Agrícola: Elaboração técnica, organização cadastral e instrução completa de proposta de crédito rural para custeio de lavoura no âmbito do PRONAF, abrangendo orçamento de insumos, adubação, defensivos, tratos culturais e colheita, com conferência documental e acompanhamento até a análise bancária.',
        'itens': [
            'COMBUSTÍVEL E ENERGIA PARA CUSTEIO',
            'CUSTEIO ADUBOS E CORRETIVOS',
            'CUSTEIO COLHEITA',
            'CUSTEIO DEFENSIVOS E INSUMOS AGRÍCOLAS',
            'CUSTEIO MANUTENÇÃO DE LAVOURA',
            'CUSTEIO MÃO DE OBRA E SERVIÇOS AGRÍCOLAS',
            'CUSTEIO SEMENTES E MUDAS',
        ],
    },
    'PRONAF - CUSTEIO PECUÁRIO': {
        'linha': 'PRONAF',
        'descricao': 'Linha PRONAF — Serviço de Custeio Pecuário: Preparação, enquadramento e instrução técnica de proposta de custeio pecuário no âmbito do PRONAF, contemplando alimentação do rebanho, sanidade animal, manejo e manutenção de pastagens, com conferência de documentação e suporte junto à instituição financeira.',
        'itens': [
            'AQUISIÇÃO DE BEZERROS / ANIMAIS PARA RECRIA',
            'CUSTEIO PRODUÇÃO LEITEIRA',
            'INSEMINAÇÃO ARTIFICIAL E MANEJO REPRODUTIVO',
            'MANUTENÇÃO DE PASTAGENS E SILAGEM',
            'RAÇÃO, SAL MINERAL E SUPLEMENTAÇÃO',
            'VACINAS E MEDICAMENTOS VETERINÁRIOS',
        ],
    },
    'PRONAF - INVESTIMENTO (MAIS ALIMENTOS)': {
        'linha': 'PRONAF',
        'descricao': 'Linha PRONAF — Serviço de Investimento Rural (Mais Alimentos): Elaboração de projeto técnico e instrução de proposta de investimento no âmbito do PRONAF para modernização da propriedade familiar, abrangendo máquinas, benfeitorias, infraestrutura produtiva, formação de lavouras ou aquisição de matrizes, conforme orçamentos apresentados.',
        'itens': [
            'CAMINHONETE / VEÍCULO UTILITÁRIO',
            'CERCA E BENFEITORIAS',
            'CONSTRUÇÃO / REFORMA DE CASA RURAL',
            'CONSTRUÇÃO DE GRANJA',
            'CURRAL (CONSTRUÇÃO / REFORMA)',
            'DRONE AGRÍCOLA',
            'ENERGIA SOLAR (SISTEMA FOTOVOLTAICO)',
            'GALPÃO / ARMAZÉM RURAL',
            'IMPLEMENTOS AGRÍCOLAS',
            'IRRIGAÇÃO',
            'LAVADOR DE CAFÉ',
            'LAVOURA - RECAPA / ESQUELETAMENTO',
            'MATRIZES BOVINAS (LEITE / CORTE)',
            'MOTOCICLETA RURAL',
            'ORDENHADEIRA MECÂNICA',
            'PLANTIO / FORMAÇÃO DE LAVOURA',
            'PRÉ-LIMPEZA E BENEFICIAMENTO DE CAFÉ',
            'PULVERIZADOR',
            'SECADOR DE CAFÉ',
            'TANQUE DE RESFRIAMENTO DE LEITE',
            'TERREIRO DE CIMENTO',
            'TRATOR AGRÍCOLA',
        ],
    },
    'PRONAMP - COMERCIALIZAÇÃO': {
        'linha': 'COMERCIALIZAÇÃO',
        'descricao': 'Linha PRONAMP — Serviço de Crédito de Comercialização: Preparação e instrução de proposta voltada à estocagem, garantia de preços e escoamento planejado da produção agropecuária, com conferência de estoques, documentação fiscal e encaminhamento ao banco.',
        'itens': [
            'DESCONTO DE DUPLICATA RURAL / NPR',
            'ESTOCAGEM DE CAFÉ / GRÃOS (FEE)',
            'GARANTIA DE PREÇO E ESCOAMENTO DA PRODUÇÃO',
            'PRÉ-COMERCIALIZAÇÃO DE SAFRA',
        ],
    },
    'PRONAMP - CPR': {
        'linha': 'CPR',
        'descricao': 'Linha CPR (Cédula de Produto Rural) — Serviço de Estruturação de CPR: Organização cadastral, conferência de garantias, cálculo de capacidade produtiva e instrução da operação de Cédula de Produto Rural (física ou financeira) para antecipação de receita e financiamento da safra.',
        'itens': [
            'ANTECIPAÇÃO DE RECEITA DE SAFRA',
            'CAPITAL DE GIRO / CUSTEIO VIA CPR',
            'CPR FINANCEIRA (LIQUIDAÇÃO EM DINHEIRO)',
            'CPR FÍSICA (ENTREGA DE CAFÉ / GRÃOS)',
        ],
    },
    'PRONAMP - CUSTEIO AGRÍCOLA': {
        'linha': 'PRONAMP',
        'descricao': 'Linha PRONAMP — Serviço de Custeio Agrícola: Elaboração técnica e organização de proposta de crédito de custeio agrícola destinada ao médio produtor rural (PRONAMP), incluindo enquadramento de renda, orçamento da atividade financiada, conferência de documentos do imóvel e protocolo junto ao agente financeiro.',
        'itens': [
            'CUSTEIO ADUBOS E CORRETIVOS',
            'CUSTEIO COLHEITA',
            'CUSTEIO DEFENSIVOS E INSUMOS AGRÍCOLAS',
            'CUSTEIO MANUTENÇÃO DE LAVOURA',
            'CUSTEIO SEMENTES E MUDAS',
            'CUSTEIO SILAGEM E FORRAGEM',
            'SERVIÇOS MECANIZADOS DE CUSTEIO',
        ],
    },
    'PRONAMP - CUSTEIO PECUÁRIO': {
        'linha': 'PRONAMP',
        'descricao': 'Linha PRONAMP — Serviço de Custeio Pecuário: Preparação e instrução técnica de proposta de custeio pecuário na linha PRONAMP, com levantamento de rebanho, orçamento de nutrição, sanidade e pastagens, além da conferência documental necessária à aprovação bancária.',
        'itens': [
            'AQUISIÇÃO DE ANIMAIS PARA RECRIA / ENGORDA',
            'CUSTEIO PECUÁRIA LEITEIRA',
            'MANUTENÇÃO DE PASTAGENS',
            'MEDICAMENTOS, VACINAS E SANIDADE ANIMAL',
            'RAÇÃO, CONCENTRADO E SILAGEM',
        ],
    },
    'PRONAMP - INDUSTRIALIZAÇÃO': {
        'linha': 'INDUSTRIALIZAÇÃO',
        'descricao': 'Linha PRONAMP — Serviço de Crédito para Industrialização Rural: Organização técnica e documental de proposta para beneficiamento, agregação de valor e processamento agroindustrial na propriedade rural, conforme projeto, licenças e orçamentos apresentados.',
        'itens': [
            'AGROINDÚSTRIA / EQUIPAMENTOS DE PROCESSAMENTO',
            'BENEFICIAMENTO E EMBALAGEM DE PRODUTOS RURAIS',
            'CÂMARA FRIA E ARMAZENAGEM REFRIGERADA',
            'LATICÍNIO / QUEIJARIA ARTESANAL',
            'TORREFAÇÃO E MOAGEM DE CAFÉ',
        ],
    },
    'PRONAMP - INOVAGRO': {
        'linha': 'INOVAGRO',
        'descricao': 'Linha INOVAGRO — Serviço de Inovação Tecnológica na Propriedade Rural: Preparação técnica e instrução de proposta vinculada ao INOVAGRO para incorporação de tecnologias de automação, agricultura de precisão, drones, energia renovável, genética animal e gestão moderna na propriedade rural.',
        'itens': [
            'AGRICULTURA DE PRECISÃO (GPS / PILOTO AUTOMÁTICO)',
            'DRONE AGRÍCOLA / PULVERIZAÇÃO',
            'ENERGIA SOLAR / BIODIGESTOR',
            'ESTAÇÃO METEOROLÓGICA E SENSORES',
            'ESTUFA AGRÍCOLA AUTOMATIZADA',
            'MELHORAMENTO GENÉTICO / FIV',
            'ORDENHA ROBOTIZADA / RESFRIAMENTO AUTOMATIZADO',
            'SOFTWARE E AUTOMAÇÃO RURAL',
        ],
    },
    'PRONAMP - INVESTIMENTO': {
        'linha': 'PRONAMP',
        'descricao': 'Linha PRONAMP — Serviço de Investimento Rural: Elaboração de projeto técnico e instrução de proposta de investimento rural para médio produtor (PRONAMP), abrangendo infraestrutura produtiva, formação ou renovação de lavouras, benfeitorias, energia solar, máquinas ou aquisição de matrizes.',
        'itens': [
            'BENEFICIAMENTO E PRÉ-LIMPEZA DE CAFÉ',
            'CAMINHONETE UTILITÁRIA',
            'CERCA E COCHEIRA',
            'CONSTRUÇÃO / REFORMA DE CASA RURAL',
            'CONSTRUÇÃO DE GRANJA',
            'CORREÇÃO INTENSIVA DE SOLO',
            'CURRAL (CONSTRUÇÃO / REFORMA)',
            'ENERGIA SOLAR (SISTEMA FOTOVOLTAICO)',
            'GALPÃO / ARMAZÉM RURAL',
            'LAVADOR DE CAFÉ',
            'LAVOURA - RECAPA / ESQUELETAMENTO',
            'MATRIZES E REPRODUTORES',
            'MOTOCICLETA RURAL',
            'ORDENHADEIRA MECÂNICA',
            'PLANTIO / IMPLANTAÇÃO DE LAVOURA',
            'SECADOR DE CAFÉ',
            'TANQUE DE RESFRIAMENTO DE LEITE',
            'TERREIRO DE CIMENTO',
            'TRATOR E IMPLEMENTOS AGRÍCOLAS',
        ],
    },
    'PRONAMP - MODERFROTA': {
        'linha': 'MODERFROTA',
        'descricao': 'Linha MODERFROTA (PRONAMP) — Serviço de Financiamento de Máquinas e Equipamentos: Elaboração técnica e instrução documental de proposta vinculada ao MODERFROTA para aquisição de tratores, colheitadeiras, pulverizadores e implementos agrícolas novos ou usados, conforme orçamentos e regras do BNDES/banco.',
        'itens': [
            'CARRETA AGRÍCOLA E GUINCHO',
            'COLHEITADEIRA / DERRIÇADORA / RECOLHEDORA',
            'EQUIPAMENTOS DE PREPARO DE SOLO',
            'EQUIPAMENTOS PARA BENEFICIAMENTO DE CAFÉ',
            'IMPLEMENTOS AGRÍCOLAS',
            'PLANTADEIRA / SEMEADEIRA',
            'PULVERIZADOR (AUTOPROPELIDO OU TRATORIZADO)',
            'TRATOR AGRÍCOLA (NOVO OU USADO)',
        ],
    },
    'PRONAMP - PCA (ARMAZENAGEM)': {
        'linha': 'PCA',
        'descricao': 'Linha PCA (Programa para Construção e Ampliação de Armazéns) — Serviço de Investimento em Armazenagem: Elaboração e organização técnica de proposta vinculada ao PCA para construção, ampliação ou modernização de galpões, armazéns, silos, tulhas e equipamentos de secagem e pré-limpeza de grãos e café.',
        'itens': [
            'AMPLIAÇÃO / MODERNIZAÇÃO DE ARMAZÉM',
            'ARMAZÉM CONVENCIONAL',
            'BALANÇA RODOVIÁRIA E MOEGAS',
            'EQUIPAMENTOS DE PRÉ-LIMPEZA E CLASSIFICAÇÃO',
            'GALPÃO PARA ARMAZENAGEM DE GRÃOS',
            'SECADOR DE CAFÉ / GRÃOS',
            'SILO METÁLICO / TULHA DE CAFÉ',
        ],
    },
    'PRONAMP - PROIRRIGA (IRRIGAÇÃO)': {
        'linha': 'PROIRRIGA',
        'descricao': 'Linha PROIRRIGA — Serviço de Investimento em Irrigação e Cultivo Protegido: Instrução técnica e organização documental de proposta vinculada ao PROIRRIGA para implantação, ampliação ou modernização de sistemas de irrigação, fertirrigação, reservatórios e estruturas de cultivo protegido.',
        'itens': [
            'ASPERSÃO CONVENCIONAL / MICROASPERSÃO',
            'CONJUNTO MOTOBOMBA E TUBULAÇÕES',
            'ESTUFA / CULTIVO PROTEGIDO',
            'FERTIRRIGAÇÃO E AUTOMAÇÃO DE IRRIGAÇÃO',
            'PIVÔ CENTRAL',
            'RESERVATÓRIO / BARRAGEM / POÇO ARTESIANO',
            'SISTEMA DE IRRIGAÇÃO POR GOTEJAMENTO',
        ],
    },
    'PRONAMP - RENOVAGRO (SUSTENTÁVEL)': {
        'linha': 'RENOVAGRO',
        'descricao': 'Linha RENOVAGRO (antigo Programa ABC) — Serviço de Investimento Sustentável: Elaboração e organização de proposta vinculada ao RENOVAGRO para recuperação de pastagens degradadas, sistemas ILPF, energia limpa, conservação de solo, tratamento de dejetos e regularização/adequação ambiental produtiva.',
        'itens': [
            'AGRICULTURA ORGÂNICA / BIOINSUMOS',
            'ENERGIA SOLAR / ENERGIA RENOVÁVEL',
            'PLANTIO DIRETO E CONSERVAÇÃO DE SOLO',
            'RECUPERAÇÃO DE PASTAGENS DEGRADADAS',
            'REFLORESTAMENTO / ADEQUAÇÃO AMBIENTAL (APP / RESERVA LEGAL)',
            'SISTEMA ILPF (INTEGRAÇÃO LAVOURA-PECUÁRIA-FLORESTA)',
            'TRATAMENTO DE DEJETOS / COMPOSTAGEM',
        ],
    },
}

# ============================================================================
# 6. OUTRAS LISTAS PADRÃO EM PORTUGUÊS DO BRASIL (ORDEM ALFABÉTICA A–Z)
# ============================================================================
BANCOS_PADRAO = [
    'BANCO DO BRASIL',
    'BRADESCO',
    'CAIXA',
    'CRESOL',
    'SICOOB',
]

TIPOS_CLIENTE_PADRAO = [
    'ARRENDATÁRIO',
    'COMODATÁRIO',
    'PARCEIRO',
    'POSSEIRO',
    'PROPRIETÁRIO',
]

TIPOS_CREDITO_PESSOAL_PADRAO = [
    'AUTOMÁTICO',
    'BENEFÍCIO',
    'CONSIGNADO',
    'SALÁRIO',
]

TIPOS_ENVIO_PADRAO = [
    'DIGITAL/E-MAIL',
    'FÍSICO',
]

# ============================================================================
# 7. CHECKLIST DE DOCUMENTOS DA CARTA-PROPOSTA (PADRÃO DA PLANILHA)
# ============================================================================
DOCS_PROPONENTE = [
    'Identidade ou CNH',
    'Comp. de endereço (atual)',
    'Cartão do Produtor',
    'IRPF',
    'Guias (NF da Cultura)',
    'Orçamento do bem',
    'CAF/DAP (Pronaf)',
    'Cert. Casamento',
    'Identidade/CNH Cônjuge',
    'Contrato (Arrendamento, Parceria ou Comodato)',
]

DOCS_IMOVEL = [
    'CAR',
    'ITR',
    'CCIR',
    'Certidão de Inteiro Teor (atual)',
]

DOCS_COOBRIGADOS = [
    'Identidade ou CNH',
    'Identidade/CNH Cônjuge',
    'Certidão de Casamento',
    'Comp. Endereço (atual)',
]

# ============================================================================
# 8. PACOTES E DOCUMENTOS DE IMPRESSÃO (ORDEM ALFABÉTICA A–Z)
# ============================================================================
DOCUMENTOS_CLIENTE_PADRAO = [
    'NOVA PROPOSTA',
    'PRODUÇÃO',
    'ORDEM DE SERVIÇO',
    'PROTEÇÃO DE DADOS',
]

PACOTES_BANCOS = {
    'BANCO DO BRASIL': ['B. DO BRASIL', 'AUTORIZAÇÃO BB', 'SICOR'],
    'BRADESCO': ['BRADESCO', 'AUTORIZAÇÃO BRADESCO'],
    'CAIXA': ['CAIXA', 'AUTORIZAÇÃO CAIXA', 'INVEST CAIXA'],
    'CRESOL': ['CRESOL', 'AUTORIZAÇÃO CRESOL'],
    'PACOTE CLIENTE (SEM BANCO)': [],
    'SICOOB': ['SICOOB BNDES', 'AUTORIZAÇÃO SICOOB', 'SICOOB', 'TERMO SICOOB'],
}

TODOS_OS_DOCUMENTOS = [
    'AUTORIZAÇÃO BB',
    'AUTORIZAÇÃO BRADESCO',
    'AUTORIZAÇÃO CAIXA',
    'AUTORIZAÇÃO CRESOL',
    'AUTORIZAÇÃO SICOOB',
    'B. DO BRASIL',
    'BB AVAL',
    'BB CONJUGE AVAL',
    'BRADESCO',
    'CAIXA',
    'CHECKLIST DE DOCUMENTOS',
    'CRESOL',
    'GALPÃO DE GRÃOS',
    'INVEST CAIXA',
    'NOVA PROPOSTA',
    'ORDEM DE SERVIÇO',
    'PRODUÇÃO',
    'PROTEÇÃO DE DADOS',
    'SICOOB',
    'SICOOB BNDES',
    'SICOR',
    'SICOR AVAL',
    'SICOR CONJUGE AVAL',
    'TERMO SICOOB',
]

# ============================================================================
# 9. MUNICÍPIOS DE BANCOS / COOPERATIVAS — RAIO 150 KM DE DIVINO-MG (A–Z)
# ============================================================================
MUNICIPIOS_BANCOS_150KM_DIVINO = [
    'Abre Campo - MG',
    'Acaiaca - MG',
    'Afonso Cláudio - ES',
    'Alegre - ES',
    'Além Paraíba - MG',
    'Alto Caparaó - MG',
    'Alto Jequitibá - MG',
    'Alvarenga - MG',
    'Alvinópolis - MG',
    'Amparo do Serra - MG',
    'Antônio Prado de Minas - MG',
    'Aperibé - RJ',
    'Apiacá - ES',
    'Araponga - MG',
    'Argirita - MG',
    'Astolfo Dutra - MG',
    'Atílio Vivácqua - ES',
    'Barão do Monte Alto - MG',
    'Barra Longa - MG',
    'Bom Jesus do Galho - MG',
    'Bom Jesus do Itabapoana - RJ',
    'Bom Jesus do Norte - ES',
    'Brás Pires - MG',
    'Brejetuba - ES',
    'Bugre - MG',
    'Cachoeiro de Itapemirim - ES',
    'Caiana - MG',
    'Cajuri - MG',
    'Cambuci - RJ',
    'Canaã - MG',
    'Caparaó - MG',
    'Caputira - MG',
    'Carangola - MG',
    'Caratinga - MG',
    'Cardoso Moreira - RJ',
    'Castelo - ES',
    'Cataguases - MG',
    'Chalé - MG',
    'Coimbra - MG',
    'Conceição de Ipanema - MG',
    'Conceição do Castelo - ES',
    'Coronel Fabriciano - MG',
    'Córrego Novo - MG',
    'Descoberto - MG',
    'Diogo de Vasconcelos - MG',
    'Dionísio - MG',
    'Divinésia - MG',
    'Divino - MG',
    'Divino de São Lourenço - ES',
    'Dom Cavati - MG',
    'Dom Silvério - MG',
    'Dona Eusébia - MG',
    'Dores do Rio Preto - ES',
    'Dores do Turvo - MG',
    'Durandé - MG',
    'Entre Folhas - MG',
    'Ervália - MG',
    'Espera Feliz - MG',
    'Estrela Dalva - MG',
    'Eugenópolis - MG',
    'Faria Lemos - MG',
    'Fervedouro - MG',
    'Goianá - MG',
    'Guaçuí - ES',
    'Guaraciaba - MG',
    'Guarani - MG',
    'Guidoval - MG',
    'Guiricema - MG',
    'Iapu - MG',
    'Ibatiba - ES',
    'Ibitirama - ES',
    'Imbé de Minas - MG',
    'Inhapim - MG',
    'Ipanema - MG',
    'Ipatinga - MG',
    'Irupi - ES',
    'Italva - RJ',
    'Itamarati de Minas - MG',
    'Itaocara - RJ',
    'Itaperuna - RJ',
    'Iúna - ES',
    'Jequeri - MG',
    'Jerônimo Monteiro - ES',
    'Laje do Muriaé - RJ',
    'Lajinha - MG',
    'Laranja da Terra - ES',
    'Laranjal - MG',
    'Leopoldina - MG',
    'Luisburgo - MG',
    'Manhuaçu - MG',
    'Manhumirim - MG',
    'Marliéria - MG',
    'Martins Soares - MG',
    'Matipó - MG',
    'Mercês - MG',
    'Mimoso do Sul - ES',
    'Miracema - RJ',
    'Miradouro - MG',
    'Miraí - MG',
    'Muniz Freire - ES',
    'Muqui - ES',
    'Muriaé - MG',
    'Mutum - MG',
    'Natividade - RJ',
    'Oratórios - MG',
    'Orizânia - MG',
    'Palma - MG',
    'Patrocínio do Muriaé - MG',
    'Paula Cândido - MG',
    'Pedra Bonita - MG',
    'Pedra do Anta - MG',
    'Pedra Dourada - MG',
    'Piedade de Caratinga - MG',
    'Piedade de Ponte Nova - MG',
    "Pingo-d'Água - MG",
    'Piranga - MG',
    'Pirapetinga - MG',
    'Piraúba - MG',
    'Pocrane - MG',
    'Ponte Nova - MG',
    'Porciúncula - RJ',
    'Porto Firme - MG',
    'Presidente Bernardes - MG',
    'Raul Soares - MG',
    'Recreio - MG',
    'Reduto - MG',
    'Rio Casca - MG',
    'Rio Doce - MG',
    'Rio Novo - MG',
    'Rio Pomba - MG',
    'Rochedo de Minas - MG',
    'Rodeiro - MG',
    'Rosário da Limeira - MG',
    'Santa Bárbara do Leste - MG',
    'Santa Cruz do Escalvado - MG',
    'Santa Margarida - MG',
    'Santa Rita de Minas - MG',
    'Santana de Cataguases - MG',
    'Santana do Manhuaçu - MG',
    'Santo Antônio de Pádua - RJ',
    'Santo Antônio do Aventureiro - MG',
    'Santo Antônio do Grama - MG',
    'São Domingos das Dores - MG',
    'São Domingos do Prata - MG',
    'São Fidélis - RJ',
    'São Francisco do Glória - MG',
    'São Geraldo - MG',
    'São João do Manhuaçu - MG',
    'São João do Oriente - MG',
    'São João Nepomuceno - MG',
    'São José de Ubá - RJ',
    'São José do Calçado - ES',
    'São José do Goiabal - MG',
    'São José do Mantimento - MG',
    'São Miguel do Anta - MG',
    'São Pedro dos Ferros - MG',
    'São Sebastião da Vargem Alegre - MG',
    'São Sebastião do Anta - MG',
    'Sem-Peixe - MG',
    'Senador Firmino - MG',
    'Senhora de Oliveira - MG',
    'Sericita - MG',
    'Silveirânia - MG',
    'Simonésia - MG',
    'Tabuleiro - MG',
    'Taparuba - MG',
    'Teixeiras - MG',
    'Timóteo - MG',
    'Tocantins - MG',
    'Tombos - MG',
    'Ubá - MG',
    'Ubaporanga - MG',
    'Urucânia - MG',
    'Vargem Alegre - MG',
    'Vargem Alta - ES',
    'Varre-Sai - RJ',
    'Venda Nova do Imigrante - ES',
    'Vermelho Novo - MG',
    'Viçosa - MG',
    'Vieiras - MG',
    'Visconde do Rio Branco - MG',
    'Volta Grande - MG',
]

# ============================================================================
# 10. ADMINISTRADORES MASTER E TIPOS DE AUTORIZAÇÕES POR USUÁRIO (A–Z)
# ============================================================================
ADMIN_MASTER_EMAILS = [
    'regularizeassessoriarural@gmail.com',
    'regularizesulmg@gmail.com',
]

ADMIN_EMAILS_PADRAO = list(ADMIN_MASTER_EMAILS)

PERMISSOES_DESCRICAO = {
    'criar_editar_proposta': 'Criar e editar propostas / clientes / análise produtiva',
    'aplicar_desconto_os': 'Conceder desconto na Ordem de Serviço (faixa abaixo de 2,00% ou desconto manual)',
    'gerar_pdf': 'Gerar e baixar PDFs (pacotes bancários e documentos avulsos)',
    'ver_historico_todos': 'Ver propostas de TODA a equipe no Histórico (desmarcado = vê apenas as próprias)',
    'editar_proposta_outros': 'Abrir e editar propostas criadas por outros atendentes',
    'exportar_excel': 'Exportar histórico de propostas para Excel (.xlsx)',
    'cadastrar_contabilidade': 'Cadastrar novas contabilidades parceiras',
    'gerenciar_usuarios': 'Acesso ao Painel do Admin (adicionar usuários e liberar autorizações)',
}

PERFIS_AUTORIZACAO = {
    'ADMIN': {
        'rotulo': 'Administrador (Acesso Total)',
        'permissoes': {'criar_editar_proposta': True, 'aplicar_desconto_os': True, 'gerar_pdf': True, 'ver_historico_todos': True, 'editar_proposta_outros': True, 'exportar_excel': True, 'cadastrar_contabilidade': True, 'gerenciar_usuarios': True},
    },
    'ATENDENTE': {
        'rotulo': 'Atendente Padrão (Cria propostas e PDFs; desconto só com liberação do Admin)',
        'permissoes': {'criar_editar_proposta': True, 'aplicar_desconto_os': False, 'gerar_pdf': True, 'ver_historico_todos': False, 'editar_proposta_outros': False, 'exportar_excel': False, 'cadastrar_contabilidade': True, 'gerenciar_usuarios': False},
    },
    'CONSULTA': {
        'rotulo': 'Somente Consulta / Impressão (Não altera nem salva propostas)',
        'permissoes': {'criar_editar_proposta': False, 'aplicar_desconto_os': False, 'gerar_pdf': True, 'ver_historico_todos': True, 'editar_proposta_outros': False, 'exportar_excel': False, 'cadastrar_contabilidade': False, 'gerenciar_usuarios': False},
    },
    'PERSONALIZADO': {
        'rotulo': 'Personalizado (Admin escolhe cada autorização manualmente)',
        'permissoes': {'criar_editar_proposta': True, 'aplicar_desconto_os': False, 'gerar_pdf': True, 'ver_historico_todos': False, 'editar_proposta_outros': False, 'exportar_excel': False, 'cadastrar_contabilidade': False, 'gerenciar_usuarios': False},
    },
    'SUPERVISOR': {
        'rotulo': 'Supervisor / Gerente (Tudo exceto gerenciar usuários)',
        'permissoes': {'criar_editar_proposta': True, 'aplicar_desconto_os': True, 'gerar_pdf': True, 'ver_historico_todos': True, 'editar_proposta_outros': True, 'exportar_excel': True, 'cadastrar_contabilidade': True, 'gerenciar_usuarios': False},
    },
}
