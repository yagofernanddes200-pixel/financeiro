"""
core.py — Lógica pura do app "Finanças Didáticas" (sem nenhuma dependência do Streamlit).

Este módulo concentra funções auxiliares de data/período, carregamento e salvamento
de dados do usuário, e as regras de negócio de saldo/fatura (incluindo a reconstrução
mensal usada no "Extrato do Mês"). Foi extraído de app.py para reduzir o tamanho do
arquivo principal e deixar mais fácil localizar e testar essas regras isoladamente.

Nada aqui chama `st.*` — são todas funções puras que recebem e devolvem dados comuns
(dict, str, float etc.), então podem ser importadas e testadas sem rodar o Streamlit.

PERSISTÊNCIA: por padrão, os dados são salvos em arquivos .json locais (bom para testes,
mas o Streamlit Cloud apaga esses arquivos sempre que o servidor reinicia/dorme). Para
persistência de verdade — que sobrevive a qualquer reinicialização do servidor — chame
`configurar_firestore(credenciais)` uma vez, bem no início do app, passando as credenciais
de uma conta de serviço do Firebase. A partir daí, todo carregamento/salvamento passa a
usar o Firestore (banco de dados na nuvem do Google) automaticamente, com cada perfil de
usuário (Yago, Binete, etc.) guardado como um documento separado.
"""

import json
import os
import hashlib
from datetime import datetime

# Cliente do Firestore, configurado (opcionalmente) via configurar_firestore().
# Enquanto for None, o app usa arquivos .json locais como já fazia antes.
_db_firestore = None
_COLECAO_FIRESTORE = "usuarios_financas"


def configurar_firestore(credenciais_dict):
    """
    Liga a persistência em nuvem (Firestore). Chame isso uma única vez, bem no início do
    app (antes de qualquer carregar_dados_usuario/salvar_dados_usuario), passando um dict
    com as credenciais da conta de serviço do Firebase (o conteúdo do arquivo .json que o
    Firebase gera, já carregado com json.loads).

    Se isso nunca for chamado (ou se a configuração falhar), o app continua funcionando
    normalmente com arquivos .json locais — só que, nesse caso, os dados não sobrevivem a
    uma reinicialização do servidor no Streamlit Cloud.
    """
    global _db_firestore
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(dict(credenciais_dict))
        firebase_admin.initialize_app(cred)
    _db_firestore = firestore.client()


def firestore_ativo():
    """Diz se a persistência em nuvem está ligada (True) ou se está usando arquivo local (False)."""
    return _db_firestore is not None


# --- FUNÇÕES DE AUXÍLIO PARA DATAS ---
def get_proximos_meses(data_inicial, parcelas):
    """Retorna uma lista de strings 'AAAA-MM' para as parcelas futuras."""
    datas = []
    ano = data_inicial.year
    mes = data_inicial.month
    
    for i in range(parcelas):
        datas.append(f"{ano}-{mes:02d}")
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
    return datas


def formatar_data_br(data_iso):
    """Converte 'AAAA-MM-DD' para 'DD/MM/AAAA'. Retorna o original se não conseguir converter."""
    try:
        return datetime.strptime(str(data_iso), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(data_iso)


def periodo_anterior(periodo):
    """Recebe 'AAAA-MM' e retorna o período do mês anterior."""
    ano, mes = map(int, periodo.split("-"))
    mes -= 1
    if mes < 1:
        mes = 12
        ano -= 1
    return f"{ano}-{mes:02d}"


def periodo_seguinte(periodo):
    """Recebe 'AAAA-MM' e retorna o período do mês seguinte."""
    ano, mes = map(int, periodo.split("-"))
    mes += 1
    if mes > 12:
        mes = 1
        ano += 1
    return f"{ano}-{mes:02d}"


def calcular_periodo_fatura(data_iso, dia_fechamento):
    """
    Calcula em qual fatura (AAAA-MM) uma compra no cartão cai, considerando o dia de fechamento.
    Se a compra ocorreu NO dia do fechamento ou depois, ela entra na fatura do mês seguinte.
    """
    try:
        data_compra = datetime.strptime(str(data_iso), "%Y-%m-%d")
    except (ValueError, TypeError):
        return str(data_iso)[:7]

    periodo_atual = f"{data_compra.year}-{data_compra.month:02d}"
    if data_compra.day >= int(dia_fechamento):
        return periodo_seguinte(periodo_atual)
    return periodo_atual


def obter_dados_cartao(dados, nome_cartao):
    return next((c for c in dados.get("cartoes", []) if c["nome"] == nome_cartao), None)


def pertence_periodo_cartao(item, periodo):
    """
    Verifica se um lançamento pertence a um período (AAAA-MM).
    Usa o campo 'periodo_fatura' (calculado a partir do fechamento do cartão) quando existir;
    caso contrário, cai de volta para a data literal do lançamento.
    """
    return item.get("periodo_fatura", str(item["data"])[:7]) == periodo


def emprestimo_pendente_no_periodo(item, periodo):
    """
    Diz se um empréstimo/dívida de terceiro estava em aberto NAQUELE mês específico —
    não existe antes de ter sido criado, e deixa de contar a partir do mês em que foi pago.
    """
    if str(item["data"])[:7] > periodo:
        return False  # ainda não tinha sido feito naquele mês
    if not item.get("pago"):
        return True
    data_pagamento = item.get("data_pagamento", item["data"])
    return str(data_pagamento)[:7] > periodo


def hash_resposta(resposta):
    return hashlib.sha256(resposta.strip().lower().encode("utf-8")).hexdigest()


def calcular_total_recorrentes_no_periodo(dados, periodo):
    """
    Soma o valor de todas as despesas recorrentes (aba Gastos, tipo "Recorrente") que
    estavam ativas em um período (AAAA-MM) — ou seja, já tinham começado e ainda não
    tinham sido encerradas naquele mês —, usando o valor específico daquele mês
    (valores_override) quando ele existir, ou o valor padrão da recorrência.

    Isso é usado para que "Meus Gastos" no Resumo e nos relatórios inclua também as
    despesas recorrentes do mês (elas ficam numa lista separada de `gastos_fixos`,
    então precisam ser somadas à parte).
    """
    total = 0.0
    for r in dados.get("gastos_recorrentes", []):
        if r["inicio"] <= periodo and (r.get("fim") is None or periodo < r["fim"]):
            total += r.get("valores_override", {}).get(periodo, r["valor"])
    return total


PERGUNTAS_SEGURANCA_PADRAO = [
    "Qual o nome do seu primeiro animal de estimação?",
    "Qual o nome da cidade onde você nasceu?",
    "Qual o nome dos seus filhos?",
    "Qual o apelido que você tinha na infância?",
    "Personalizada (escrever a minha própria pergunta)"
]

# --- CONTROLE DE MULTIPERFIS E SEGURANÇA ---
def obter_caminho_dados(usuario):
    nome_limpo = usuario.lower().strip().replace(" ", "_")
    return f"dados_financeiros_{nome_limpo}.json"

def carregar_dados_usuario(usuario):
    if _db_firestore is not None:
        doc_id = usuario.lower().strip().replace(" ", "_")
        doc = _db_firestore.collection(_COLECAO_FIRESTORE).document(doc_id).get()
        dados = doc.to_dict() if doc.exists else {}
        if dados is None:
            dados = {}
    else:
        caminho = obter_caminho_dados(usuario)
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
            except:
                dados = {}
        else:
            dados = {}
        
    # Inicialização padrão de chaves para segurança
    pin_padrao = "123456" if usuario.lower() == "yago" else "654321" if usuario.lower() == "binete" else "123456"
    dados.setdefault("pin", pin_padrao)
    dados.setdefault("receitas", [])
    dados.setdefault("gastos_fixos", [])
    dados.setdefault("gastos_avulsos", [])
    dados.setdefault("gastos_terceiros_cartao", [])
    dados.setdefault("gastos_terceiros_emprestimo", [])
    dados.setdefault("transferencias", [])
    
    # MIGRAR CONTAS ANTIGAS PARA ESTRUTURA DINÂMICA
    if "contas" not in dados:
        saldo_isolada = 0.0
        saldo_caixinha = 0.0
        if "conta_isolada" in dados:
            saldo_isolada = dados["conta_isolada"].get("saldo_principal", 0.0)
            saldo_caixinha = dados["conta_isolada"].get("caixinha_nu", 0.0)
            
        dados["contas"] = [
            {"nome": "Nu", "saldo": 0.0, "tipo": "Normal"},
            {"nome": "PicPay", "saldo": 0.0, "tipo": "Normal"},
            {"nome": "Inter", "saldo": 0.0, "tipo": "Normal"},
            {"nome": "Dinheiro", "saldo": 0.0, "tipo": "Normal"},
            {"nome": "Banco Pan (Guardado)", "saldo": saldo_isolada, "tipo": "Guardado"},
            {"nome": "Caixinha NU (Guardado)", "saldo": saldo_caixinha, "tipo": "Guardado"}
        ]
        
    # MIGRAR CARTOES DE CRÉDITO DINÂMICOS
    if "cartoes" not in dados:
        dados["cartoes"] = [
            {"nome": "Cartão Nu", "fatura": 0.0, "fechamento": 1, "vencimento": 10},
            {"nome": "Cartão PicPay", "fatura": 0.0, "fechamento": 1, "vencimento": 10}
        ]

    # Garante que cartões antigos (criados antes desta versão) tenham fechamento/vencimento
    for c in dados.get("cartoes", []):
        c.setdefault("fechamento", 1)
        c.setdefault("vencimento", 10)

    # Migrar/garantir lista de gastos fixos recorrentes ("para sempre")
    dados.setdefault("gastos_recorrentes", [])
    for rec in dados["gastos_recorrentes"]:
        rec.setdefault("fim", None)
        rec.setdefault("pagamentos", {})
        rec.setdefault("valores_override", {})
        if "periodos_lancados" not in rec:
            # Migração: meses que já estavam marcados como pagos no sistema antigo já tiveram a
            # fatura lançada de verdade — marcamos como já lançados para não cobrar em dobro.
            if rec.get("metodo_pagamento") == "Cartao":
                rec["periodos_lancados"] = [p for p, v in rec["pagamentos"].items() if v]
            else:
                rec["periodos_lancados"] = []

    # Migrar/garantir lista de dívidas recorrentes de terceiros no cartão (ex: assinatura dividida)
    dados.setdefault("terceiros_recorrentes", [])
    for rec in dados["terceiros_recorrentes"]:
        rec.setdefault("fim", None)
        rec.setdefault("pagamentos", {})
        rec.setdefault("valores_override", {})

    # Log de recebimentos de terceiros (para reconstrução de extrato mensal)
    dados.setdefault("recebimentos_terceiros", [])

    # Log de movimentações de fatura (para reconstrução mensal, igual ao extrato de contas)
    dados.setdefault("fatura_movimentos", [])

    # Migrar pergunta de segurança (recuperação de senha)
    dados.setdefault("pergunta_seguranca", None)
    dados.setdefault("resposta_hash", None)
        
    # Compatibilidade com faturas de cartão nas despesas antigas
    for r in dados.get("receitas", []):
        r.setdefault("conta", "Nu")
        
    for g in dados.get("gastos_fixos", []):
        g.setdefault("metodo_pagamento", "Saldo")
        g.setdefault("conta", "Nu")
        g.setdefault("cartao_nome", "Cartão Nu")
        
    for a in dados.get("gastos_avulsos", []):
        a.setdefault("metodo_pagamento", "Saldo")
        a.setdefault("conta", "Nu")
        a.setdefault("cartao_nome", "Cartão Nu")
        
    for t in dados.get("gastos_terceiros_cartao", []):
        t.setdefault("cartao_nome", "Cartão Nu")
        
    return dados

def salvar_dados_usuario(usuario, dados):
    if _db_firestore is not None:
        doc_id = usuario.lower().strip().replace(" ", "_")
        _db_firestore.collection(_COLECAO_FIRESTORE).document(doc_id).set(dados)
    else:
        caminho = obter_caminho_dados(usuario)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)

# --- AUXILIARES DE MOVIMENTAÇÃO DE SALDO & FATURAS ---
def alterar_saldo(dados, nome_conta, valor, operacao="somar"):
    for conta in dados.setdefault("contas", []):
        if conta["nome"] == nome_conta:
            if operacao == "somar":
                conta["saldo"] += valor
            elif operacao == "subtrair":
                conta["saldo"] -= valor
            return True
    return False

def alterar_fatura(dados, nome_cartao, valor, operacao="somar", data=None):
    if data is None:
        data = str(datetime.now().date())
    for cartao in dados.setdefault("cartoes", []):
        if cartao["nome"] == nome_cartao:
            valor_efetivo = valor if operacao == "somar" else -valor
            if operacao == "somar":
                cartao["fatura"] += valor
            elif operacao == "subtrair":
                novo_valor = cartao["fatura"] - valor
                if novo_valor < 0:
                    valor_efetivo = -cartao["fatura"]
                    novo_valor = 0.0
                cartao["fatura"] = novo_valor
            dados.setdefault("fatura_movimentos", []).append({
                "cartao_nome": nome_cartao,
                "data": data,
                "valor": valor_efetivo
            })
            return True
    return False


def calcular_fatura_cartao_no_periodo(dados, nome_cartao, periodo_fim):
    """
    Reconstrói a fatura de um cartão até o FIM de um período (AAAA-MM), a partir do
    log de movimentações (mesma lógica usada para o saldo das contas).
    """
    cartao_obj = obter_dados_cartao(dados, nome_cartao)
    if not cartao_obj:
        return 0.0

    movimentos = [m for m in dados.get("fatura_movimentos", []) if m.get("cartao_nome") == nome_cartao]
    ajuste_total = sum(m["valor"] for m in movimentos)
    ajuste_ate_periodo = sum(m["valor"] for m in movimentos if str(m["data"])[:7] <= periodo_fim)

    base = cartao_obj["fatura"] - ajuste_total
    fatura_reconstruida = base + ajuste_ate_periodo
    return max(fatura_reconstruida, 0.0)


def calcular_saldo_conta_no_periodo(dados, nome_conta, periodo_fim):
    """
    Reconstrói o saldo de uma conta até o FIM de um período (AAAA-MM), a partir do
    histórico de lançamentos já registrados (mesma lógica de um extrato bancário:
    saldo atual real, menos tudo que ainda não tinha acontecido até aquele mês).

    OBS: usa a data/'período' nominal de cada lançamento (a data que você escolheu ao
    cadastrar) como a data do movimento no livro-razão.
    """
    conta_obj = next((c for c in dados.get("contas", []) if c["nome"] == nome_conta), None)
    if not conta_obj:
        return 0.0

    def per(data_str):
        return str(data_str)[:7]

    ajuste_total = 0.0        # soma de TODOS os movimentos já conhecidos (qualquer data)
    ajuste_ate_periodo = 0.0  # soma apenas dos movimentos com data <= periodo_fim

    def registrar(valor, data_evento):
        nonlocal ajuste_total, ajuste_ate_periodo
        ajuste_total += valor
        if per(data_evento) <= periodo_fim:
            ajuste_ate_periodo += valor

    for r in dados.get("receitas", []):
        if r.get("conta") == nome_conta:
            registrar(r["valor"], r["data"])

    for g in dados.get("gastos_fixos", []):
        if g.get("metodo_pagamento") == "Saldo" and g.get("conta") == nome_conta and g.get("pago"):
            registrar(-g["valor"], g["data"])

    for rec in dados.get("gastos_recorrentes", []):
        if rec.get("metodo_pagamento") == "Saldo" and rec.get("conta") == nome_conta:
            for p, pago_flag in rec.get("pagamentos", {}).items():
                if pago_flag:
                    v = rec.get("valores_override", {}).get(p, rec["valor"])
                    registrar(-v, f"{p}-01")

    for a in dados.get("gastos_avulsos", []):
        if a.get("metodo_pagamento") == "Saldo" and a.get("conta") == nome_conta:
            registrar(-a["valor"], a["data"])

    for t in dados.get("transferencias", []):
        if t.get("origem") == nome_conta:
            registrar(-t["valor"], t["data"])
        if t.get("destino") == nome_conta:
            registrar(t["valor"], t["data"])

    for e in dados.get("gastos_terceiros_emprestimo", []):
        if e.get("conta_origem") == nome_conta:
            registrar(-e["valor"], e["data"])

    for rt in dados.get("recebimentos_terceiros", []):
        if rt.get("conta_destino") == nome_conta:
            registrar(rt["valor"], rt["data"])

    saldo_base = conta_obj["saldo"] - ajuste_total
    return saldo_base + ajuste_ate_periodo
