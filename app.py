import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
import re
import hashlib
from datetime import datetime, timedelta

# Configuração da página para celular (Samsung A15 e iPhone)
st.set_page_config(
    page_title="Finanças Didáticas",
    page_icon="💰",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- CONFIGURAÇÃO DE ESTILO: MODO ESCURO PREMIUM ---
st.markdown("""
<style>
    /* Estilo geral da página */
    .stApp {
        background-color: #121214;
        color: #E1E1E6;
    }
    
    /* Cabeçalho */
    h1, h2, h3, h4, h5, h6 {
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif;
    }
    
    /* Cards Customizados */
    .card-principal {
        background-color: #202024;
        padding: 18px;
        border-radius: 12px;
        margin-bottom: 15px;
        border-left: 5px solid #8257E5;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .card-didatico {
        background-color: #1A1A1E;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 15px;
        border-left: 5px solid #3867D6;
        font-size: 0.9em;
        line-height: 1.5;
        color: #C4C4CC;
    }
    .card-receita {
        background-color: #1A2E26;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #26DE81;
    }
    .card-gasto {
        background-color: #2D1A1E;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #FF4757;
    }
    .titulo-secao {
        color: #FFFFFF;
        font-weight: bold;
        margin-top: 20px;
        border-bottom: 1px solid #29292E;
        padding-bottom: 8px;
    }
    
    /* Botões */
    .stButton>button {
        background-color: #8257E5 !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 10px 20px !important;
        font-weight: bold !important;
        width: 100%;
        transition: background-color 0.2s;
    }
    .stButton>button:hover {
        background-color: #9466FF !important;
    }
    .stButton>button:disabled {
        background-color: #3A3A40 !important;
        color: #7A7A82 !important;
        cursor: not-allowed;
    }
    
    /* Inputs */
    div[data-baseweb="input"] {
        background-color: #202024 !important;
        border-color: #29292E !important;
    }
    input {
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

from core import (
    get_proximos_meses,
    formatar_data_br,
    periodo_anterior,
    periodo_seguinte,
    calcular_periodo_fatura,
    obter_dados_cartao,
    pertence_periodo_cartao,
    emprestimo_pendente_no_periodo,
    hash_resposta,
    PERGUNTAS_SEGURANCA_PADRAO,
    obter_caminho_dados,
    carregar_dados_usuario,
    salvar_dados_usuario,
    alterar_saldo,
    alterar_fatura,
    calcular_saldo_conta_no_periodo,
    calcular_fatura_cartao_no_periodo,
    calcular_total_recorrentes_no_periodo,
    configurar_firestore,
    firestore_ativo,
)
from relatorios import (
    gerar_relatorio_mensal_pdf,
    gerar_relatorio_mensal_docx,
    gerar_relatorio_anual_pdf,
    gerar_relatorio_anual_docx,
)


# --- LIGAR PERSISTÊNCIA EM NUVEM (FIRESTORE), SE CONFIGURADA NOS SECRETS ---
# Se o segredo "firebase.credentials_json" existir (colado nas configurações do app no
# Streamlit Cloud), os dados passam a ser salvos no Firestore em vez de arquivos locais,
# sobrevivendo a qualquer reinicialização do servidor. Se não existir, o app continua
# funcionando normalmente com arquivos .json locais, sem quebrar nada.
if not firestore_ativo():
    try:
        if "firebase" in st.secrets and "credentials_json" in st.secrets["firebase"]:
            _credenciais_firebase = json.loads(st.secrets["firebase"]["credentials_json"])
            configurar_firestore(_credenciais_firebase)
    except Exception as _erro_firebase:
        st.warning(
            f"⚠️ Não consegui conectar ao Firestore, usando armazenamento local temporário. "
            f"Detalhe técnico: {_erro_firebase}"
        )

# --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
if "usuario_ativo" not in st.session_state:
    params = st.query_params
    usuario_url = params.get("user", "Yago").title()
    st.session_state.usuario_ativo = usuario_url

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

usuario_atual = st.session_state.usuario_ativo
dados = carregar_dados_usuario(usuario_atual)

# --- LANÇAMENTO AUTOMÁTICO DE COMPRAS NO CARTÃO (Única/Parcelada) ---
# Roda antes de qualquer aba ser desenhada, para que "Faturas em Aberto" e "Meus Gastos" no
# Resumo já reflitam qualquer compra no cartão cujo mês da fatura já chegou — uma compra no
# cartão é sempre cobrada automaticamente, não depende de o usuário marcar nada como "pago".
_periodo_hoje_auto = f"{datetime.now().year}-{datetime.now().month:02d}"
_houve_lancamento_auto = False
for _item_auto in dados.get("gastos_fixos", []):
    if (
        _item_auto.get("metodo_pagamento") == "Cartao"
        and not _item_auto.get("pago")
        and _item_auto.get("periodo_fatura", "9999-99") <= _periodo_hoje_auto
    ):
        alterar_fatura(dados, _item_auto.get("cartao_nome", ""), _item_auto["valor"], "somar", data=_item_auto["data"])
        _item_auto["pago"] = True
        _houve_lancamento_auto = True
if _houve_lancamento_auto:
    salvar_dados_usuario(usuario_atual, dados)

# --- CABEÇALHO DO APP ---
col_logo, col_titulo = st.columns([1, 4])
with col_logo:
    if os.path.exists("app_logo_financeiro.png"):
        st.image("app_logo_financeiro.png", width=70)
    else:
        st.markdown("<h1 style='font-size: 50px; margin: 0;'>💰</h1>", unsafe_allow_html=True)

with col_titulo:
    st.title("Finanças Didáticas")
    st.caption("Controle financeiro premium e descomplicado")

# --- TELA DE LOGIN / SEGURANÇA ---
if not st.session_state.autenticado:
    st.markdown(f"### 🔒 Acesso Restrito - Perfil: **{usuario_atual}**")
    st.markdown("Por segurança, digite sua senha de 6 dígitos para acessar seus dados.")
    
    tentativas_key = f"tentativas_login_{usuario_atual}"
    if tentativas_key not in st.session_state:
        st.session_state[tentativas_key] = 0

    bloqueado = st.session_state[tentativas_key] >= 5

    if bloqueado:
        st.error("🚫 Muitas tentativas incorretas. Recarregue a página para tentar novamente.")

    pin_digitado = st.text_input("Digite o PIN de 6 dígitos:", type="password", max_chars=6, disabled=bloqueado)
    
    col_btn_login, col_btn_perfil = st.columns(2)
    with col_btn_login:
        if st.button("Entrar 🔓", disabled=bloqueado):
            if pin_digitado == dados.get("pin", "123456"):
                st.session_state.autenticado = True
                st.session_state[tentativas_key] = 0
                st.success("Acesso liberado!")
                st.rerun()
            else:
                st.session_state[tentativas_key] += 1
                restantes = 5 - st.session_state[tentativas_key]
                if restantes > 0:
                    st.error(f"PIN incorreto! Tentativas restantes: {restantes}.")
                else:
                    st.rerun()
                
    with col_btn_perfil:
        novo_usuario = st.selectbox("Trocar de Perfil:", ["Yago", "Binete", "Criar Novo Perfil"])
        if novo_usuario == "Criar Novo Perfil":
            st.markdown("---")
            st.markdown("**Criar Novo Perfil Independente**")
            novo_nome = st.text_input("Nome do Novo Usuário:")
            novo_pin = st.text_input("Escolha um PIN de 6 dígitos (somente números):", type="password", max_chars=6)

            pergunta_escolhida = st.selectbox("Escolha uma pergunta de segurança (para recuperar o PIN se esquecer):", PERGUNTAS_SEGURANCA_PADRAO)
            pergunta_final = pergunta_escolhida
            if pergunta_escolhida == PERGUNTAS_SEGURANCA_PADRAO[-1]:
                pergunta_final = st.text_input("Digite sua pergunta personalizada:")
            resposta_seguranca = st.text_input("Resposta da pergunta de segurança:")

            if st.button("Criar Perfil e Acessar 🚀"):
                if novo_nome and len(novo_pin) == 6 and novo_pin.isdigit() and pergunta_final and resposta_seguranca:
                    dados_novos = carregar_dados_usuario(novo_nome)
                    dados_novos["pin"] = novo_pin
                    dados_novos["pergunta_seguranca"] = pergunta_final
                    dados_novos["resposta_hash"] = hash_resposta(resposta_seguranca)
                    salvar_dados_usuario(novo_nome, dados_novos)
                    st.session_state.usuario_ativo = novo_nome.title()
                    st.session_state.autenticado = True
                    st.query_params["user"] = novo_nome.lower()
                    st.success(f"Perfil de {novo_nome} criado e logado!")
                    st.rerun()
                else:
                    st.error("Preencha nome, PIN de 6 dígitos, a pergunta e a resposta de segurança.")
        elif novo_usuario != usuario_atual:
            st.session_state.usuario_ativo = novo_usuario
            st.query_params["user"] = novo_usuario.lower()
            st.rerun()

    # --- ESQUECI MEU PIN (RECUPERAÇÃO POR PERGUNTA DE SEGURANÇA) ---
    st.markdown("---")
    with st.expander("🔑 Esqueci meu PIN"):
        if not dados.get("pergunta_seguranca") or not dados.get("resposta_hash"):
            st.info(
                "Este perfil ainda não tem uma pergunta de segurança configurada. "
                "Faça login normalmente e configure uma na aba ⚙️ Senha para poder recuperar o acesso no futuro."
            )
        else:
            st.write(f"**Pergunta de segurança:** {dados['pergunta_seguranca']}")
            resposta_tentativa = st.text_input("Sua resposta:", key="resposta_recuperacao")
            novo_pin_rec = st.text_input("Novo PIN (6 dígitos):", type="password", max_chars=6, key="novo_pin_rec")
            confirmar_pin_rec = st.text_input("Confirme o novo PIN:", type="password", max_chars=6, key="conf_pin_rec")
            if st.button("Redefinir PIN"):
                if hash_resposta(resposta_tentativa) != dados["resposta_hash"]:
                    st.error("Resposta incorreta.")
                elif not (novo_pin_rec.isdigit() and len(novo_pin_rec) == 6):
                    st.error("O novo PIN deve ter exatamente 6 números.")
                elif novo_pin_rec != confirmar_pin_rec:
                    st.error("Os dois PINs digitados não coincidem.")
                else:
                    dados["pin"] = novo_pin_rec
                    salvar_dados_usuario(usuario_atual, dados)
                    st.session_state[tentativas_key] = 0
                    st.success("PIN redefinido com sucesso! Você já pode entrar com o novo PIN.")
                    st.rerun()

    st.stop()

# --- SELETOR DE MÊS E ANO (PLANEJAMENTO SEM LIMITES) ---
st.markdown("---")
col_perf, col_m, col_a = st.columns([2, 2, 2])

with col_perf:
    st.markdown(f"👤 **{usuario_atual}**")
    if st.button("Sair / Bloquear 🔒"):
        st.session_state.autenticado = False
        st.rerun()

with col_m:
    meses_lista = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ]
    mes_atual_nome = meses_lista[datetime.now().month - 1]
    mes_selecionado = st.selectbox("Selecione o Mês:", meses_lista, index=datetime.now().month - 1)
    mes_num = meses_lista.index(mes_selecionado) + 1

with col_a:
    anos_lista = list(range(2025, 2036))
    ano_selecionado = st.selectbox("Selecione o Ano:", anos_lista, index=anos_lista.index(datetime.now().year))

periodo_ativo = f"{ano_selecionado}-{mes_num:02d}"

# --- NAVEGAÇÃO POR ABAS (Mobile Friendly) ---
abas = st.tabs(["📊 Resumo", "💵 Ganhos", "🏠 Gastos", "👥 Terceiros", "💳 Saldos", "🔒 Guardado", "⚙️ Senha"])

# ----------------- ABA 1: RESUMO GERAL & RELATÓRIOS -----------------
with abas[0]:
    st.markdown(f"<h3 class='titulo-secao'>📊 Painel Financeiro ({mes_selecionado}/{ano_selecionado})</h3>", unsafe_allow_html=True)
    
    saldo_normal_contas = sum(
        calcular_saldo_conta_no_periodo(dados, c["nome"], periodo_ativo)
        for c in dados.get("contas", []) if c.get("tipo", "Normal") == "Normal"
    )
    saldo_guardado_contas = sum(
        calcular_saldo_conta_no_periodo(dados, c["nome"], periodo_ativo)
        for c in dados.get("contas", []) if c.get("tipo", "Normal") == "Guardado"
    )
    faturas_abertas = sum(calcular_fatura_cartao_no_periodo(dados, c["nome"], periodo_ativo) for c in dados.get("cartoes", []))
    patrimonio_liquido = saldo_normal_contas + saldo_guardado_contas - faturas_abertas

    col_pl1, col_pl2 = st.columns(2)
    col_pl1.metric(f"🏦 Contas Normais ({mes_selecionado}/{ano_selecionado})", f"R$ {saldo_normal_contas:,.2f}")
    col_pl2.metric(f"🔒 Guardado/Poupança ({mes_selecionado}/{ano_selecionado})", f"R$ {saldo_guardado_contas:,.2f}")

    col_pl3, col_pl4 = st.columns(2)
    col_pl3.metric(f"Faturas em Aberto ({mes_selecionado}/{ano_selecionado})", f"R$ {faturas_abertas:,.2f}")
    col_pl4.metric("Patrimônio Líquido", f"R$ {patrimonio_liquido:,.2f}")
    st.caption("Saldos de contas e faturas refletem o mês/ano selecionado no topo — uma fatura de junho não aparece como aberta em maio.")
    st.markdown("---")


    tipo_relatorio = st.radio("Escolha o tipo de Relatório:", ["Relatório Mensal", "Relatório Anual"], horizontal=True)
    
    if tipo_relatorio == "Relatório Mensal":
        # Filtrar dados do mês selecionado
        receitas_mes = [r for r in dados.get("receitas", []) if r["data"].startswith(periodo_ativo)]
        gastos_fixos_mes = [g for g in dados.get("gastos_fixos", []) if pertence_periodo_cartao(g, periodo_ativo)]
        gastos_avulsos_mes = [g for g in dados.get("gastos_avulsos", []) if pertence_periodo_cartao(g, periodo_ativo)]
        
        total_receitas = sum(r["valor"] for r in receitas_mes)
        total_fixos = sum(g["valor"] for g in gastos_fixos_mes)
        total_avulsos = sum(g["valor"] for g in gastos_avulsos_mes)
        total_recorrentes = calcular_total_recorrentes_no_periodo(dados, periodo_ativo)
        total_gastos = total_fixos + total_avulsos + total_recorrentes
        saldo_livre = total_receitas - total_gastos
        
        # Calcular total guardado nas contas do tipo "Guardado"
        total_guardado = sum(c["saldo"] for c in dados["contas"] if c["tipo"] == "Guardado")
        
        # Terceiros pendentes
        unpaid_cartao = [t for t in dados.get("gastos_terceiros_cartao", []) if not t["pago"]]
        unpaid_emprestimo = [e for e in dados.get("gastos_terceiros_emprestimo", []) if not e["pago"]]
        
        total_cartao_terceiros = sum(t["valor"] for t in unpaid_cartao if pertence_periodo_cartao(t, periodo_ativo))
        total_emprestimos_pendentes = sum(e["valor"] for e in dados.get("gastos_terceiros_emprestimo", []) if emprestimo_pendente_no_periodo(e, periodo_ativo))
        
        # Métricas na tela
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric(label="Minhas Receitas (+)", value=f"R$ {total_receitas:,.2f}")
            st.metric(label="Meus Gastos (-)", value=f"R$ {total_gastos:,.2f}")
        with col_m2:
            st.metric(label="Saldo do Mês (Livre)", value=f"R$ {saldo_livre:,.2f}", delta=f"R$ {saldo_livre:,.2f}" if saldo_livre >= 0 else f"R$ {saldo_livre:,.2f}")
            st.metric(label="Total Guardado", value=f"R$ {total_guardado:,.2f}")
            
        # Alertas de Terceiros
        st.markdown("#### 👥 Dinheiro de Terceiros a Receber:")
        c_t1, c_t2 = st.columns(2)
        with c_t1:
            if total_cartao_terceiros > 0:
                st.warning(f"💳 **Cartão de Crédito:**\n\nR$ {total_cartao_terceiros:,.2f} pendentes neste mês.")
            else:
                st.success("💳 **Cartão de Crédito:**\n\nNenhum reembolso pendente.")
        with c_t2:
            if total_emprestimos_pendentes > 0:
                st.warning(f"💸 **Empréstimos:**\n\nR$ {total_emprestimos_pendentes:,.2f} a receber.")
            else:
                st.success("💸 **Empréstimos:**\n\nTodos pagos!")
                
        # Gráficos do Mês (Container para Empilhar no Celular e Colunas no PC)
        cont_graf = st.container()
        with cont_graf:
            # Gráfico 1: Divisão das Despesas (Pizza)
            if total_gastos > 0:
                st.markdown("#### 📈 Divisão das Despesas (Fixos vs. Recorrentes vs. Avulsos)")
                df_pizza = pd.DataFrame([
                    {"Categoria": "Únicos/Parcelados", "Valor": total_fixos},
                    {"Categoria": "Recorrentes", "Valor": total_recorrentes},
                    {"Categoria": "Avulsos (histórico)", "Valor": total_avulsos}
                ])
                df_pizza = df_pizza[df_pizza["Valor"] > 0]
                fig = px.pie(df_pizza, values="Valor", names="Categoria", hole=0.4,
                             color_discrete_sequence=["#8257E5", "#3867D6", "#FF4757"])
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    font_color="#FFFFFF",
                    margin=dict(t=10, b=10, l=10, r=10),
                    height=220
                )
                st.plotly_chart(fig, use_container_width=True)
                
            # Gráfico 2: Alocação Geral Macro (Ganhos vs. Despesas vs. Guardados do Mês)
            economias_mes = 0.0
            for t in dados.get("transferencias", []):
                if t["data"].startswith(periodo_ativo):
                    dest_tipo = next((c["tipo"] for c in dados["contas"] if c["nome"] == t["destino"]), "Normal")
                    orig_tipo = next((c["tipo"] for c in dados["contas"] if c["nome"] == t["origem"]), "Normal")
                    if dest_tipo == "Guardado" and orig_tipo == "Normal":
                        economias_mes += t["valor"]
                        
            st.markdown("#### 📊 Alocação Macro Mensal (Fluxos)")
            df_macro = pd.DataFrame([
                {"Fluxo": "Ganhos", "Valor": total_receitas, "Cor": "#26DE81"},
                {"Fluxo": "Despesas", "Valor": total_gastos, "Cor": "#FF4757"},
                {"Fluxo": "Guardado", "Valor": economias_mes, "Cor": "#8257E5"}
            ])
            fig_macro = px.bar(df_macro, x="Valor", y="Fluxo", color="Fluxo", orientation="h",
                               color_discrete_map={"Ganhos": "#26DE81", "Despesas": "#FF4757", "Guardado": "#8257E5"})
            fig_macro.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font_color="#FFFFFF",
                margin=dict(t=10, b=10, l=10, r=10),
                height=200,
                showlegend=False
            )
            st.plotly_chart(fig_macro, use_container_width=True)
            
        # --- EXPORTAR RELATÓRIO MENSAL (BOTÕES) ---
        st.markdown("---")
        st.markdown("### 📥 Exportar Relatório Oficial (Mensal)")
        st.caption("Gere um relatório explicativo completo, pronto para baixar em PDF ou editar em Word.")
        
        col_pdf, col_docx = st.columns(2)
        with col_pdf:
            pdf_bytes = gerar_relatorio_mensal_pdf(dados, periodo_ativo, mes_selecionado, ano_selecionado, usuario_atual)
            st.download_button(
                label="📄 Baixar PDF",
                data=pdf_bytes,
                file_name=f"relatorio_financeiro_{usuario_atual.lower()}_{periodo_ativo}.pdf",
                mime="application/pdf"
            )
        with col_docx:
            docx_bytes = gerar_relatorio_mensal_docx(dados, periodo_ativo, mes_selecionado, ano_selecionado, usuario_atual)
            st.download_button(
                label="📝 Baixar Word (.docx)",
                data=docx_bytes,
                file_name=f"relatorio_financeiro_{usuario_atual.lower()}_{periodo_ativo}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            
    else:
        # --- RELATÓRIO ANUAL CONSOLIDADO ---
        st.markdown(f"### 📅 Relatório Anual - Ano: **{ano_selecionado}**")
        
        # Consolidar dados de todos os 12 meses do ano selecionado de forma correta
        dados_ano = []
        for m in range(1, 13):
            prefixo_busca = f"{ano_selecionado}-{m:02d}"
            rec_ano = sum(r["valor"] for r in dados.get("receitas", []) if r["data"].startswith(prefixo_busca))
            fix_ano = sum(g["valor"] for g in dados.get("gastos_fixos", []) if g["data"].startswith(prefixo_busca))
            av_ano = sum(g["valor"] for g in dados.get("gastos_avulsos", []) if g["data"].startswith(prefixo_busca))
            recorrentes_ano = calcular_total_recorrentes_no_periodo(dados, prefixo_busca)
            gastos_totais = fix_ano + av_ano + recorrentes_ano
            dados_ano.append({
                "Mês": meses_lista[m-1][:3],
                "Ganhos": rec_ano,
                "Gastos": gastos_totais
            })
            
        df_ano = pd.DataFrame(dados_ano)
        
        # Totais Anuais
        total_ganhos_ano = df_ano["Ganhos"].sum()
        total_gastos_ano = df_ano["Gastos"].sum()
        saldo_anual_acumulado = total_ganhos_ano - total_gastos_ano
        
        col_an1, col_an2, col_an3 = st.columns(3)
        col_an1.metric("Ganhos no Ano", f"R$ {total_ganhos_ano:,.2f}")
        col_an2.metric("Gastos no Ano", f"R$ {total_gastos_ano:,.2f}")
        col_an3.metric("Balanço Acumulado", f"R$ {saldo_anual_acumulado:,.2f}", 
                        delta=f"R$ {saldo_anual_acumulado:,.2f}" if saldo_anual_acumulado >= 0 else f"R$ {saldo_anual_acumulado:,.2f}")
        
        # Gráfico de Linha/Tendência Premium
        st.markdown("#### 📈 Tendência Anual (Ganhos vs. Gastos)")
        df_melted = df_ano.melt(id_vars="Mês", value_vars=["Ganhos", "Gastos"], var_name="Categoria", value_name="Valor (R$)")
        fig_trend = px.line(df_melted, x="Mês", y="Valor (R$)", color="Categoria", markers=True,
                            color_discrete_map={"Ganhos": "#26DE81", "Gastos": "#FF4757"})
        fig_trend.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color="#FFFFFF",
            margin=dict(t=10, b=10, l=10, r=10),
            height=280
        )
        st.plotly_chart(fig_trend, use_container_width=True)
        
        # --- EXPORTAR RELATÓRIO ANUAL (BOTÕES) ---
        st.markdown("---")
        st.markdown("### 📥 Exportar Relatório Oficial (Anual)")
        st.caption("Gere o consolidado completo de todos os meses do ano em PDF ou Word.")
        
        col_pdf_an, col_docx_an = st.columns(2)
        with col_pdf_an:
            pdf_an_bytes = gerar_relatorio_anual_pdf(dados, ano_selecionado, meses_lista, usuario_atual)
            st.download_button(
                label="📄 Baixar PDF Anual",
                data=pdf_an_bytes,
                file_name=f"relatorio_anual_{usuario_atual.lower()}_{ano_selecionado}.pdf",
                mime="application/pdf"
            )
        with col_docx_an:
            docx_an_bytes = gerar_relatorio_anual_docx(dados, ano_selecionado, meses_lista, usuario_atual)
            st.download_button(
                label="📝 Baixar Word Anual (.docx)",
                data=docx_an_bytes,
                file_name=f"relatorio_anual_{usuario_atual.lower()}_{ano_selecionado}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

# ----------------- ABA 2: GANHOS (RECEITAS) -----------------
with abas[1]:
    st.markdown("<h3 class='titulo-secao'>💵 Registro de Ganhos</h3>", unsafe_allow_html=True)
    
    with st.form("form_receita", clear_on_submit=True):
        st.markdown("**Adicionar Nova Receita**")
        desc = st.text_input("Descrição (Ex: Salário, PIX, Freelance)")
        val = st.number_input("Valor (R$)", min_value=0.0, step=50.0, format="%.2f")
        
        # Selecionar em qual conta depositar
        contas_nomes = [c["nome"] for c in dados["contas"]]
        conta_dest = st.selectbox("Depositar na Conta:", contas_nomes)
        
        data_padrao = datetime(ano_selecionado, mes_num, min(datetime.now().day, 28))
        data_rec = st.date_input("Data do Recebimento", data_padrao, format="DD/MM/YYYY")
        
        enviar = st.form_submit_button("Salvar Receita")
        if enviar and desc and val > 0:
            nova_rec = {"data": str(data_rec), "descricao": desc, "valor": val, "conta": conta_dest}
            dados.setdefault("receitas", []).append(nova_rec)
            
            # Atualiza saldo automaticamente
            alterar_saldo(dados, conta_dest, val, "somar")
            
            salvar_dados_usuario(usuario_atual, dados)
            st.success(f"Receita adicionada e valor depositado na conta {conta_dest}!")
            st.rerun()

    # Mostrar Receitas do Mês Selecionado
    receitas_mes = [r for r in dados.get("receitas", []) if r["data"].startswith(periodo_ativo)]
    if receitas_mes:
        st.markdown("#### Suas Receitas Registradas neste Mês")

        filtro_rec = st.text_input("🔎 Buscar por descrição:", key="filtro_receitas")

        for idx, item in enumerate(dados["receitas"]):
            if not item["data"].startswith(periodo_ativo):
                continue
            if filtro_rec and filtro_rec.lower() not in item["descricao"].lower():
                continue

            col_d, col_v, col_del = st.columns([3, 2, 1])
            col_d.markdown(f"**{item['descricao']}**\n\n*{formatar_data_br(item['data'])} — {item.get('conta', 'Não especificada')}*")
            col_v.markdown(f"R$ {item['valor']:,.2f}")

            confirm_key = f"confirma_del_rec_{idx}"
            if col_del.button("🗑️", key=f"del_rec_{idx}", help="Excluir este lançamento"):
                st.session_state[confirm_key] = True

            if st.session_state.get(confirm_key):
                st.warning(f"Excluir '{item['descricao']}' (R$ {item['valor']:,.2f})? Isso também estorna o valor da conta '{item.get('conta', '')}'.")
                c_sim, c_nao = st.columns(2)
                if c_sim.button("Sim, excluir", key=f"conf_sim_rec_{idx}"):
                    alterar_saldo(dados, item.get("conta", ""), item["valor"], "subtrair")
                    dados["receitas"].pop(idx)
                    salvar_dados_usuario(usuario_atual, dados)
                    del st.session_state[confirm_key]
                    st.rerun()
                if c_nao.button("Cancelar", key=f"conf_nao_rec_{idx}"):
                    del st.session_state[confirm_key]
                    st.rerun()
            st.markdown("---")

        with st.expander("⚠️ Apagar todo o histórico de receitas deste mês"):
            st.caption("Atenção: isso remove todos os lançamentos do mês, sem estornar os saldos.")
            confirma_limpar_rec = st.checkbox("Confirmo que quero apagar tudo", key="chk_limpar_rec")
            if st.button("Limpar Histórico de Receitas (Mês)", key="limpar_rec", disabled=not confirma_limpar_rec):
                dados["receitas"] = [r for r in dados.get("receitas", []) if not r["data"].startswith(periodo_ativo)]
                salvar_dados_usuario(usuario_atual, dados)
                st.rerun()

# ----------------- ABA 3: MEUS GASTOS (únicos, parcelados e recorrentes) -----------------
with abas[2]:
    st.markdown("<h3 class='titulo-secao'>🏠 Meus Gastos</h3>", unsafe_allow_html=True)
    st.caption("Gastos do dia a dia, parcelados ou recorrentes — tudo em um só lugar.")

    if "fixo_form_key" not in st.session_state:
        st.session_state.fixo_form_key = 0
    fk = st.session_state.fixo_form_key

    st.markdown("**Adicionar Gasto Fixo**")
    desc = st.text_input("Descrição do Gasto (Ex: Aluguel, Parcela de Notebook, Academia)", key=f"desc_fixo_{fk}")
    val = st.number_input("Valor Mensal (R$)", min_value=0.0, step=10.0, format="%.2f", key=f"val_fixo_{fk}")

    # INTEGRAÇÃO CARTÃO DE CRÉDITO DINÂMICO (fora do form para reagir na hora)
    metodo_p = st.selectbox("Forma de Pagamento:", ["Saldo em Conta", "Cartão de Crédito"], key=f"metodo_fixo_{fk}")
    if metodo_p == "Saldo em Conta":
        conta_pagamento = st.selectbox("Pagar com a Conta:", [c["nome"] for c in dados["contas"]], key=f"conta_fixo_{fk}")
        cartao_pagamento = "Não se aplica"
    else:
        conta_pagamento = "Não se aplica"
        cartao_pagamento = st.selectbox("Pagar com o Cartão:", [c["nome"] for c in dados["cartoes"]], key=f"cartao_fixo_{fk}")

    tipo_despesa_fixa = st.radio(
        "Tipo de Despesa:",
        ["Única (só este mês)", "Parcelada (número fixo de parcelas)", "Recorrente (todo mês, até eu encerrar)"],
        key=f"tipo_fixo_{fk}"
    )
    st.caption("Use 'Recorrente' para gastos como academia, assinaturas ou aluguel: ela continua aparecendo todo mês até você encerrar.")

    total_parc = 1
    if tipo_despesa_fixa == "Parcelada (número fixo de parcelas)":
        total_parc = st.number_input("Número total de parcelas:", min_value=2, max_value=48, value=2, step=1, key=f"parc_fixo_{fk}")

    data_gasto_unico = None
    if tipo_despesa_fixa == "Única (só este mês)":
        data_padrao_unico = datetime(ano_selecionado, mes_num, min(datetime.now().day, 28))
        data_gasto_unico = st.date_input(
            "Data do Gasto", data_padrao_unico, format="DD/MM/YYYY", key=f"data_unico_{fk}_{periodo_ativo}"
        )
        st.caption("No cartão, a data escolhida decide em qual fatura o gasto cai (antes ou depois do fechamento).")

    eh_cartao = (metodo_p == "Cartão de Crédito")
    eh_recorrente = (tipo_despesa_fixa == "Recorrente (todo mês, até eu encerrar)")
    eh_unico = (tipo_despesa_fixa == "Única (só este mês)")

    if eh_cartao:
        if eh_recorrente:
            st.caption("💳 Como é recorrente no cartão, ela entra automaticamente na fatura todo mês — não precisa marcar como paga.")
        else:
            st.caption("💳 Compra no cartão: entra automaticamente na fatura correspondente assim que ela abrir (igual uma compra de verdade no cartão) — não precisa marcar como paga.")
        pago = False  # não decide o lançamento no cartão — isso é sempre automático (ver bloco de lançamento abaixo)
    elif eh_unico:
        st.caption("💰 Gasto único: o valor já sai do saldo da conta agora, como uma compra à vista.")
        pago = True
    else:
        pago = st.checkbox("Marcar já como pago neste mês (1ª parcela)?", key=f"pago_fixo_{fk}")

    if st.button("Salvar Despesa", key=f"salvar_fixo_{fk}"):
        if desc and val > 0:
            data_inicial = datetime(ano_selecionado, mes_num, 1)
            metodo_salvar = "Saldo" if metodo_p == "Saldo em Conta" else "Cartao"

            if tipo_despesa_fixa == "Recorrente (todo mês, até eu encerrar)":
                periodo_inicio_rec = periodo_ativo
                if metodo_salvar == "Cartao":
                    cartao_obj_rec = obter_dados_cartao(dados, cartao_pagamento)
                    if cartao_obj_rec:
                        # Usa o dia de hoje (dentro do mês selecionado) pra saber se, dado o
                        # fechamento do cartão, essa recorrência já entra na fatura deste mês
                        # ou só a partir do mês seguinte — igual já fazemos pra Única/Parcelada.
                        data_referencia_rec = f"{periodo_ativo}-{min(datetime.now().day, 28):02d}"
                        periodo_inicio_rec = calcular_periodo_fatura(data_referencia_rec, cartao_obj_rec.get("fechamento", 1))
                novo_recorrente = {
                    "id": f"rec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    "descricao": desc,
                    "valor": val,
                    "metodo_pagamento": metodo_salvar,
                    "conta": conta_pagamento,
                    "cartao_nome": cartao_pagamento,
                    "inicio": periodo_inicio_rec,
                    "fim": None,
                    "pagamentos": {periodo_inicio_rec: pago},
                    "valores_override": {},
                    "periodos_lancados": []
                }
                dados.setdefault("gastos_recorrentes", []).append(novo_recorrente)
                if metodo_salvar == "Saldo" and pago:
                    alterar_saldo(dados, conta_pagamento, val, "subtrair")
                # Cartão: não lança aqui — o lançamento automático na fatura acontece
                # assim que o mês aparecer na tela (ver bloco "Mostrar Gastos Recorrentes" abaixo)

            elif tipo_despesa_fixa == "Parcelada (número fixo de parcelas)":
                lista_periodos = get_proximos_meses(data_inicial, total_parc)
                for i, periodo in enumerate(lista_periodos):
                    # No cartão, nenhuma parcela é lançada aqui na hora — cada uma é debitada
                    # automaticamente na fatura certa, quando aquele mês chegar (ver bloco de
                    # lançamento automático logo abaixo, na exibição da lista).
                    status_pago_parc = (pago if i == 0 else False) if metodo_salvar == "Saldo" else False
                    novo_gasto = {
                        "data": f"{periodo}-01",
                        "descricao": f"{desc} (Parc. {i+1}/{total_parc})",
                        "valor": val,
                        "pago": status_pago_parc,
                        "metodo_pagamento": metodo_salvar,
                        "conta": conta_pagamento,
                        "cartao_nome": cartao_pagamento,
                        "periodo_fatura": periodo
                    }
                    dados.setdefault("gastos_fixos", []).append(novo_gasto)
                    if metodo_salvar == "Saldo" and status_pago_parc:
                        alterar_saldo(dados, conta_pagamento, val, "subtrair")
            else:
                data_evento_unico = str(data_gasto_unico) if data_gasto_unico else f"{periodo_ativo}-01"
                periodo_fat_fixo = periodo_ativo
                if metodo_salvar == "Cartao":
                    cartao_obj_fixo = obter_dados_cartao(dados, cartao_pagamento)
                    if cartao_obj_fixo:
                        periodo_fat_fixo = calcular_periodo_fatura(data_evento_unico, cartao_obj_fixo.get("fechamento", 1))
                novo_gasto = {
                    "data": data_evento_unico,
                    "descricao": desc,
                    "valor": val,
                    # Saldo: já sai da conta na hora (pago=True sempre, é uma compra "à vista").
                    # Cartão: começa como não lançado — o bloco de lançamento automático (abaixo,
                    # na listagem) debita da fatura assim que o mês correspondente chegar.
                    "pago": False if metodo_salvar == "Cartao" else True,
                    "metodo_pagamento": metodo_salvar,
                    "conta": conta_pagamento,
                    "cartao_nome": cartao_pagamento,
                    "periodo_fatura": periodo_fat_fixo
                }
                dados.setdefault("gastos_fixos", []).append(novo_gasto)
                if metodo_salvar == "Saldo":
                    alterar_saldo(dados, conta_pagamento, val, "subtrair")
                # Cartão: não lança aqui — o bloco de lançamento automático (na listagem
                # abaixo) debita da fatura assim que o mês correspondente chegar.
                
            salvar_dados_usuario(usuario_atual, dados)
            st.session_state.fixo_form_key += 1
            st.success("Despesa cadastrada com sucesso!")
            st.rerun()
        else:
            st.error("Preencha a descrição e um valor maior que zero.")

    # Mostrar Gastos Recorrentes ativos neste mês
    recorrentes_ativos = [
        r for r in dados.get("gastos_recorrentes", [])
        if r["inicio"] <= periodo_ativo and (r["fim"] is None or periodo_ativo < r["fim"])
    ]
    if recorrentes_ativos:
        st.markdown("#### 🔁 Despesas Recorrentes (Todo Mês)")
        for rec in recorrentes_ativos:
            valor_mes_rec = rec["valores_override"].get(periodo_ativo, rec["valor"])
            pago_mes_rec = rec["pagamentos"].get(periodo_ativo, False)
            rec_metodo = rec.get("metodo_pagamento", "Saldo")
            rec_local = rec.get("conta", "Nu") if rec_metodo == "Saldo" else rec.get("cartao_nome", "Cartão Nu")
            rec.setdefault("periodos_lancados", [])

            # CARTÃO: lança automaticamente na fatura assim que o mês aparece na tela (sem precisar marcar "pago"),
            # mas só até o mês real de hoje — não pré-lança cobranças de meses futuros que ainda não chegaram.
            periodo_hoje = f"{datetime.now().year}-{datetime.now().month:02d}"
            if rec_metodo == "Cartao" and periodo_ativo not in rec["periodos_lancados"] and periodo_ativo <= periodo_hoje:
                alterar_fatura(dados, rec_local, valor_mes_rec, "somar", data=f"{periodo_ativo}-01")
                rec["periodos_lancados"].append(periodo_ativo)
                salvar_dados_usuario(usuario_atual, dados)

            col_d, col_v, col_p = st.columns([2, 1, 1])
            col_d.markdown(f"**{rec['descricao']}** 🔁\n\n*({rec_local})*")
            col_v.markdown(f"R$ {valor_mes_rec:,.2f}")

            if rec_metodo == "Cartao":
                col_p.caption("💳 Cobrada automaticamente")
            else:
                novo_pago_rec = col_p.checkbox("Pago", value=pago_mes_rec, key=f"rec_pago_{rec['id']}_{periodo_ativo}")
                if novo_pago_rec != pago_mes_rec:
                    if novo_pago_rec:
                        alterar_saldo(dados, rec_local, valor_mes_rec, "subtrair")
                    else:
                        alterar_saldo(dados, rec_local, valor_mes_rec, "somar")
                    rec["pagamentos"][periodo_ativo] = novo_pago_rec
                    salvar_dados_usuario(usuario_atual, dados)
                    st.rerun()

            with st.expander(f"⚙️ Gerenciar '{rec['descricao']}'"):
                novo_valor_rec = st.number_input(
                    f"Valor de {mes_selecionado}/{ano_selecionado}:", min_value=0.0,
                    value=float(valor_mes_rec), step=5.0, format="%.2f", key=f"editval_rec_{rec['id']}"
                )
                if st.button("Salvar novo valor deste mês", key=f"btn_editval_rec_{rec['id']}"):
                    diff_rec = novo_valor_rec - valor_mes_rec
                    if rec_metodo == "Cartao":
                        # Já foi lançado automaticamente acima nesta mesma execução; ajusta pela diferença
                        if diff_rec != 0:
                            alterar_fatura(dados, rec_local, diff_rec, "somar", data=f"{periodo_ativo}-01")
                    elif pago_mes_rec and diff_rec != 0:
                        alterar_saldo(dados, rec_local, diff_rec, "subtrair")
                    rec["valores_override"][periodo_ativo] = novo_valor_rec
                    salvar_dados_usuario(usuario_atual, dados)
                    st.rerun()

                st.markdown("---")
                st.caption("Encerrar esta recorrência: ela deixa de aparecer a partir do mês escolhido (meses anteriores continuam no histórico).")
                if st.button(f"🛑 Encerrar a partir de {mes_selecionado}/{ano_selecionado}", key=f"encerrar_rec_{rec['id']}"):
                    rec["fim"] = periodo_ativo
                    salvar_dados_usuario(usuario_atual, dados)
                    st.success("Recorrência encerrada a partir deste mês.")
                    st.rerun()

                st.markdown("---")
                confirma_del_rec = st.checkbox("Confirmo que quero excluir esta recorrência por completo", key=f"chk_del_rec_{rec['id']}")
                if st.button("🗑️ Excluir recorrência por completo", key=f"del_rec_{rec['id']}", disabled=not confirma_del_rec):
                    # Estorna tudo que essa recorrência já tinha lançado antes de apagar, senão
                    # o valor fica "preso" na fatura/saldo mesmo depois de excluída.
                    if rec_metodo == "Cartao":
                        for periodo_lancado in rec.get("periodos_lancados", []):
                            valor_lancado = rec.get("valores_override", {}).get(periodo_lancado, rec["valor"])
                            alterar_fatura(dados, rec_local, valor_lancado, "subtrair", data=f"{periodo_lancado}-01")
                    else:
                        for periodo_pago, pago_flag in rec.get("pagamentos", {}).items():
                            if pago_flag:
                                valor_pago = rec.get("valores_override", {}).get(periodo_pago, rec["valor"])
                                alterar_saldo(dados, rec_local, valor_pago, "somar")
                    dados["gastos_recorrentes"] = [r for r in dados["gastos_recorrentes"] if r["id"] != rec["id"]]
                    salvar_dados_usuario(usuario_atual, dados)
                    st.success("Recorrência excluída e valores já lançados foram estornados.")
                    st.rerun()
            st.markdown("---")

    # Mostrar recorrências encerradas que poderiam ser reativadas (apenas informativo, dentro de um expander)
    recorrentes_encerradas = [r for r in dados.get("gastos_recorrentes", []) if r["fim"] is not None and r["fim"] <= periodo_ativo]
    if recorrentes_encerradas:
        with st.expander("↩️ Recorrências encerradas (reativar se necessário)"):
            for rec in recorrentes_encerradas:
                col_re1, col_re2 = st.columns([3, 1])
                col_re1.markdown(f"**{rec['descricao']}** — encerrada a partir de {rec['fim']}")
                if col_re2.button("Reativar", key=f"reativar_{rec['id']}"):
                    rec["fim"] = None
                    salvar_dados_usuario(usuario_atual, dados)
                    st.rerun()

    # Mostrar Gastos Fixos do Mês (únicos e parcelados)
    gastos_fixos_mes = [g for g in dados.get("gastos_fixos", []) if pertence_periodo_cartao(g, periodo_ativo)]
    if gastos_fixos_mes:
        st.markdown("#### Controle de Pagamentos de Despesas Fixas / Parceladas")
        for idx, item in enumerate(dados["gastos_fixos"]):
            if pertence_periodo_cartao(item, periodo_ativo):
                col_d, col_v, col_p = st.columns([2, 1, 1])
                item_metodo = item.get("metodo_pagamento", "Saldo")
                item_local = item.get("conta", "Nu") if item_metodo == "Saldo" else item.get("cartao_nome", "Cartão Nu")
                col_d.markdown(f"**{item['descricao']}**\n\n*({item_local})*")
                col_v.markdown(f"R$ {item['valor']:,.2f}")

                if item_metodo == "Cartao":
                    # Compra no cartão: sempre automática, sem toggle manual (igual às Recorrentes).
                    if item["pago"]:
                        col_p.caption("💳 Lançada na fatura")
                    else:
                        col_p.caption("💳 Aguardando fatura abrir")
                else:
                    status_pago = col_p.checkbox("Pago", value=item["pago"], key=f"fixo_{idx}_{periodo_ativo}")
                    if status_pago != item["pago"]:
                        if status_pago:  # Marcou pago agora
                            alterar_saldo(dados, item_local, item["valor"], "subtrair")
                        else:  # Desmarcou pagamento, estorna
                            alterar_saldo(dados, item_local, item["valor"], "somar")
                        dados["gastos_fixos"][idx]["pago"] = status_pago
                        salvar_dados_usuario(usuario_atual, dados)
                        st.rerun()

                with st.expander(f"⚙️ Editar / Excluir '{item['descricao']}'"):
                    novo_valor_fixo = st.number_input(
                        "Valor desta parcela:", min_value=0.0, value=float(item["valor"]),
                        step=5.0, format="%.2f", key=f"editval_fixo_{idx}"
                    )
                    if st.button("Salvar novo valor", key=f"btn_editval_fixo_{idx}"):
                        diff_fixo = novo_valor_fixo - item["valor"]
                        if item["pago"] and diff_fixo != 0:
                            if item_metodo == "Saldo":
                                alterar_saldo(dados, item_local, diff_fixo, "subtrair")
                            else:
                                alterar_fatura(dados, item_local, diff_fixo, "somar", data=item["data"])
                        dados["gastos_fixos"][idx]["valor"] = novo_valor_fixo
                        salvar_dados_usuario(usuario_atual, dados)
                        st.rerun()

                    st.markdown("---")
                    confirma_del_fixo = st.checkbox("Confirmo que quero excluir este item", key=f"chk_del_fixo_{idx}")
                    if st.button("🗑️ Excluir este item", key=f"del_fixo_{idx}", disabled=not confirma_del_fixo):
                        if item["pago"]:
                            if item_metodo == "Saldo":
                                alterar_saldo(dados, item_local, item["valor"], "somar")
                            else:
                                alterar_fatura(dados, item_local, item["valor"], "subtrair", data=item["data"])
                        dados["gastos_fixos"].pop(idx)
                        salvar_dados_usuario(usuario_atual, dados)
                        st.rerun()
                st.markdown("---")
                    
        with st.expander("⚠️ Apagar todos os gastos fixos deste mês"):
            st.caption("Atenção: isso remove todos os lançamentos do mês, sem estornar os saldos/faturas.")
            confirma_limpar_fixos = st.checkbox("Confirmo que quero apagar tudo", key="chk_limpar_fixos")
            if st.button("Limpar Todos os Gastos Fixos (Deste Mês)", key="limpar_fixos", disabled=not confirma_limpar_fixos):
                dados["gastos_fixos"] = [g for g in dados.get("gastos_fixos", []) if not pertence_periodo_cartao(g, periodo_ativo)]
                salvar_dados_usuario(usuario_atual, dados)
                st.rerun()

# ----------------- ABA 4: GASTOS DE TERCEIROS (CONTAS DE DEVEDORES POR PESSOA) -----------------
with abas[3]:
    st.markdown("<h3 class='titulo-secao'>👥 Amigos & Terceiros (Faturas & Empréstimos)</h3>", unsafe_allow_html=True)
    
    sub_abas_terceiros = st.tabs(["➕ Cadastrar Lançamento", "👤 Contas dos Devedores", "✅ Reembolsos Recebidos"])
    
    # SUB-ABA 5.1: CADASTRAR COMPRA OU EMPRÉSTIMO
    with sub_abas_terceiros[0]:
        opcao_terc = st.radio("Selecione o tipo de Lançamento de Terceiro:", ["Compras no Meu Cartão", "Empréstimos (PIX/Dinheiro)"], horizontal=True)
        
        if opcao_terc == "Compras no Meu Cartão":
            st.markdown("**Adicionar Compra de Terceiro no seu Cartão de Crédito**")
            st.caption("Aumenta a fatura do seu cartão. A pessoa fica te devendo mensalmente.")

            if "terc_form_key" not in st.session_state:
                st.session_state.terc_form_key = 0
            fkt = st.session_state.terc_form_key

            nome = st.text_input("Nome de quem comprou:", key=f"nome_terc_{fkt}")
            desc = st.text_input("Descrição da compra (Ex: Pizza, Tênis, Netflix dividido)", key=f"desc_terc_{fkt}")
            val = st.number_input("Valor da compra/parcela (R$)", min_value=0.0, step=10.0, format="%.2f", key=f"val_terc_{fkt}")

            # Selecionar cartão utilizado
            cartao_utilizado = st.selectbox("Qual Cartão foi Utilizado?", [c["nome"] for c in dados["cartoes"]], key=f"cartao_terc_{fkt}")

            tipo_lanc_terc = st.radio(
                "Tipo de Lançamento:",
                ["Única (só este mês)", "Parcelada (número fixo de parcelas)", "Recorrente (todo mês, até eu encerrar)"],
                key=f"tipo_terc_{fkt}", horizontal=True
            )
            st.caption("Use 'Recorrente' para gastos divididos todo mês, como uma assinatura de streaming.")

            total_parc_terc = 1
            if tipo_lanc_terc == "Parcelada (número fixo de parcelas)":
                total_parc_terc = st.number_input("Número de parcelas de terceiro:", min_value=2, max_value=48, value=2, step=1, key=f"parc_terc_{fkt}")

            pago_terc = st.checkbox("Marcar já como paga esta parcela/mês?", key=f"pago_terc_{fkt}")

            if st.button("Salvar Lançamento", key=f"salvar_terc_{fkt}"):
                if nome and desc and val > 0:
                    data_inicial = datetime(ano_selecionado, mes_num, 1)
                    nome_formatado = nome.title().strip()

                    if tipo_lanc_terc == "Recorrente (todo mês, até eu encerrar)":
                        novo_terc_rec = {
                            "id": f"tercrec_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                            "nome": nome_formatado,
                            "descricao": desc,
                            "valor": val,
                            "cartao_nome": cartao_utilizado,
                            "inicio": periodo_ativo,
                            "fim": None,
                            "pagamentos": {periodo_ativo: pago_terc},
                            "valores_override": {}
                        }
                        dados.setdefault("terceiros_recorrentes", []).append(novo_terc_rec)
                        if pago_terc:
                            alterar_fatura(dados, cartao_utilizado, val, "somar", data=f"{periodo_ativo}-01")

                    elif tipo_lanc_terc == "Parcelada (número fixo de parcelas)":
                        lista_periodos = get_proximos_meses(data_inicial, total_parc_terc)
                        for i, periodo in enumerate(lista_periodos):
                            status_pago_parc = pago_terc if i == 0 else False
                            nova_compra = {
                                "data": f"{periodo}-01",
                                "nome": nome_formatado,
                                "descricao": f"{desc} (Parc. {i+1}/{total_parc_terc})",
                                "valor": val,
                                "pago": status_pago_parc,
                                "cartao_nome": cartao_utilizado,
                                "periodo_fatura": periodo
                            }
                            dados.setdefault("gastos_terceiros_cartao", []).append(nova_compra)

                            # Aumenta a fatura do cartão
                            if i == 0:
                                alterar_fatura(dados, cartao_utilizado, val, "somar", data=f"{periodo}-01")
                    else:
                        cartao_obj_terc = obter_dados_cartao(dados, cartao_utilizado)
                        periodo_fat_terc = calcular_periodo_fatura(f"{periodo_ativo}-01", cartao_obj_terc.get("fechamento", 1)) if cartao_obj_terc else periodo_ativo
                        nova_compra = {
                            "data": f"{periodo_ativo}-01",
                            "nome": nome_formatado,
                            "descricao": desc,
                            "valor": val,
                            "pago": pago_terc,
                            "cartao_nome": cartao_utilizado,
                            "periodo_fatura": periodo_fat_terc
                        }
                        dados.setdefault("gastos_terceiros_cartao", []).append(nova_compra)
                        alterar_fatura(dados, cartao_utilizado, val, "somar", data=nova_compra["data"])

                    salvar_dados_usuario(usuario_atual, dados)
                    st.session_state.terc_form_key += 1
                    st.success(f"Lançamento de cartão registrado para {nome_formatado}! Fatura do '{cartao_utilizado}' atualizada.")
                    st.rerun()
                else:
                    st.error("Preencha nome, descrição e um valor maior que zero.")
                    
        else:
            st.markdown("**Adicionar Empréstimo direto em Dinheiro ou PIX**")
            st.caption("Retira dinheiro da sua conta corrente imediatamente para dar a um terceiro.")
            
            with st.form("form_emprestimo_terceiros", clear_on_submit=True):
                nome_emp = st.text_input("Quem pediu o empréstimo?")
                desc_emp = st.text_input("Motivo do empréstimo (Ex: Empréstimo para Luz)")
                val_emp = st.number_input("Valor Emprestado (R$)", min_value=0.0, step=10.0, format="%.2f")
                
                # Selecionar de qual conta tirar o dinheiro
                conta_origem_emp = st.selectbox("Retirar Dinheiro de qual Conta/Dinheiro?", [c["nome"] for c in dados["contas"]])
                
                enviar_e = st.form_submit_button("Registrar Empréstimo")
                if enviar_e and nome_emp and val_emp > 0:
                    nome_formatado_emp = nome_emp.title().strip()
                    novo_emp = {
                        "data": str(datetime.now().date()),
                        "nome": nome_formatado_emp,
                        "descricao": desc_emp,
                        "valor": val_emp,
                        "pago": False,
                        "conta_origem": conta_origem_emp,
                        "forma_recebimento": "",
                        "conta_destino": ""
                    }
                    dados.setdefault("gastos_terceiros_emprestimo", []).append(novo_emp)
                    
                    # Deduz da conta de origem automaticamente
                    alterar_saldo(dados, conta_origem_emp, val_emp, "subtrair")
                    
                    salvar_dados_usuario(usuario_atual, dados)
                    st.success(f"Empréstimo registrado para {nome_formatado_emp}! R$ {val_emp:,.2f} deduzidos da conta '{conta_origem_emp}'.")
                    st.rerun()

    # SUB-ABA 5.2: CONTAS DOS DEVEDORES (VISTA POR PESSOA)
    with sub_abas_terceiros[1]:
        st.markdown("**Gestão de Débitos Pendentes por Devedor**")
        st.caption("Consolidação automática de contas por devedor. Clique na pessoa para ver o detalhamento ou quitar débitos parciais ou totais.")
        
        # Pegar todos os registros pendentes de cartão e empréstimo
        unpaid_cartao = [t for t in dados.get("gastos_terceiros_cartao", []) if not t["pago"]]
        unpaid_emprestimo = [e for e in dados.get("gastos_terceiros_emprestimo", []) if not e["pago"]]
        recorrentes_terc_ativos = [
            r for r in dados.get("terceiros_recorrentes", [])
            if r["inicio"] <= periodo_ativo and (r["fim"] is None or periodo_ativo < r["fim"])
        ]
        
        # Encontrar todas as pessoas com débitos ativos
        nomes_devedores = sorted(list(set(
            [t["nome"] for t in unpaid_cartao] + 
            [e["nome"] for e in unpaid_emprestimo] +
            [r["nome"] for r in recorrentes_terc_ativos]
        )))
        
        if not nomes_devedores:
            st.success("🎉 Excelente! Ninguém te deve nada neste momento.")
        else:
            for nome_dev in nomes_devedores:
                # Filtrar itens específicos desse devedor
                debitos_cartao = [t for t in unpaid_cartao if t["nome"].lower() == nome_dev.lower()]
                debitos_emp = [e for e in unpaid_emprestimo if e["nome"].lower() == nome_dev.lower()]
                debitos_rec_terc = [r for r in recorrentes_terc_ativos if r["nome"].lower() == nome_dev.lower()]

                # Valor referente a ESTE mês (parcela do mês corrente) vs. total ainda pendente em todos os meses futuros
                debitos_cartao_mes = [t for t in debitos_cartao if pertence_periodo_cartao(t, periodo_ativo)]
                total_dev_cartao_mes = sum(t["valor"] for t in debitos_cartao_mes)
                total_dev_cartao_geral = sum(t["valor"] for t in debitos_cartao)
                total_dev_emp = sum(e["valor"] for e in debitos_emp)
                total_dev_rec_pendente = sum(
                    r["valores_override"].get(periodo_ativo, r["valor"])
                    for r in debitos_rec_terc if not r["pagamentos"].get(periodo_ativo, False)
                )
                total_dev_geral = total_dev_cartao_geral + total_dev_emp + total_dev_rec_pendente
                
                # Expandível customizado por devedor com balanço
                with st.expander(f"👤 {nome_dev} — Deve no total: R$ {total_dev_geral:,.2f}"):
                    st.markdown(f"**Balanço do Devedor:**")
                    st.markdown(f"- 💳 Valor do Cartão referente a {mes_selecionado}/{ano_selecionado}: **R$ {total_dev_cartao_mes:,.2f}**")
                    if total_dev_cartao_geral > total_dev_cartao_mes:
                        st.caption(f"Total ainda pendente no cartão, somando parcelas de outros meses: R$ {total_dev_cartao_geral:,.2f}")
                    st.markdown(f"- 💸 Débitos de Empréstimos (Pix/Dinheiro): **R$ {total_dev_emp:,.2f}**")
                    if debitos_rec_terc:
                        st.markdown(f"- 🔁 Recorrentes (referente a {mes_selecionado}/{ano_selecionado}): **R$ {total_dev_rec_pendente:,.2f}**")
                    st.markdown("---")
                    
                    # Mostrar Detalhamento do Cartão
                    if debitos_cartao:
                        st.markdown("**💳 Detalhamento de Compras no Cartão:**")
                        for idx_terc, t in enumerate(dados["gastos_terceiros_cartao"]):
                            if t not in debitos_cartao:
                                continue
                            desc_visual = t["descricao"]
                            base_desc = None
                            
                            # Parser de Parcelas Restantes
                            match = re.search(r"^(.*?)\s*\(Parc\.\s*(\d+)/(\d+)\)", desc_visual)
                            if match:
                                base_desc = match.group(1).strip()
                                total_parc = int(match.group(3))
                                
                                # Buscar todas as parcelas pendentes para essa pessoa
                                parcelas_totais = [g for g in dados.get("gastos_terceiros_cartao", []) if g["nome"].lower() == nome_dev.lower() and base_desc in g["descricao"]]
                                parcelas_pendentes = [g for g in parcelas_totais if not g["pago"]]
                                desc_visual = f"{t['descricao']} *(Faltam {len(parcelas_pendentes)} de {total_parc} parcelas)*"
                                
                            col_terc_txt, col_terc_btn1, col_terc_btn2, col_terc_btn3 = st.columns([3, 1, 1, 1])
                            col_terc_txt.write(f"- **{formatar_data_br(t['data'])}**: {desc_visual} — **R$ {t['valor']:,.2f}** *({t.get('cartao_nome', 'Cartão Nu')})*")

                            conv_key = f"conv_{idx_terc}"
                            if col_terc_btn1.button("🔁 Converter", key=f"btn_{conv_key}", help="Já paguei essa parcela com meu dinheiro; a pessoa passa a me dever essa parcela como empréstimo direto."):
                                st.session_state[conv_key] = True

                            edit_key = f"editterc_{idx_terc}"
                            if col_terc_btn2.button("✏️", key=f"btn_{edit_key}", help="Editar o valor desta parcela"):
                                st.session_state[edit_key] = True

                            del_key = f"delterc_{idx_terc}"
                            if col_terc_btn3.button("🗑️", key=f"btn_{del_key}", help="Excluir este lançamento (erro ou dívida perdoada)"):
                                st.session_state[del_key] = True

                            if st.session_state.get(edit_key):
                                novo_valor_terc = st.number_input(
                                    "Novo valor desta parcela:", min_value=0.0, value=float(t["valor"]),
                                    step=1.0, format="%.2f", key=f"input_{edit_key}"
                                )
                                col_edit_sim, col_edit_nao = st.columns(2)
                                if col_edit_sim.button("Salvar novo valor", key=f"conf_{edit_key}"):
                                    diff_terc = novo_valor_terc - t["valor"]
                                    if diff_terc != 0:
                                        alterar_fatura(dados, t.get("cartao_nome", ""), diff_terc, "somar", data=t["data"])
                                    dados["gastos_terceiros_cartao"][idx_terc]["valor"] = novo_valor_terc
                                    salvar_dados_usuario(usuario_atual, dados)
                                    del st.session_state[edit_key]
                                    st.success("Valor da parcela atualizado!")
                                    st.rerun()
                                if col_edit_nao.button("Cancelar", key=f"canc_{edit_key}"):
                                    del st.session_state[edit_key]
                                    st.rerun()

                            if st.session_state.get(conv_key):
                                # Converte SOMENTE esta parcela/lançamento (as demais parcelas, se houver, continuam no cartão)
                                itens_a_converter = [t]
                                valor_total_conv = sum(g["valor"] for g in itens_a_converter)

                                st.info(f"Você está convertendo '{t['descricao']}' — R$ {valor_total_conv:,.2f} — de dívida no cartão para empréstimo direto.")
                                conta_saida_conv = st.selectbox(
                                    "De qual conta sua saiu o dinheiro para pagar essa parcela agora?",
                                    [c["nome"] for c in dados["contas"] if c["tipo"] == "Normal"],
                                    key=f"conta_{conv_key}"
                                )
                                col_conv_sim, col_conv_nao = st.columns(2)
                                if col_conv_sim.button("Confirmar conversão", key=f"conf_{conv_key}"):
                                    alterar_fatura(dados, t.get("cartao_nome", ""), valor_total_conv, "subtrair")
                                    alterar_saldo(dados, conta_saida_conv, valor_total_conv, "subtrair")
                                    dados["gastos_terceiros_cartao"] = [g for g in dados["gastos_terceiros_cartao"] if g not in itens_a_converter]
                                    dados.setdefault("gastos_terceiros_emprestimo", []).append({
                                        "data": str(datetime.now().date()),
                                        "nome": nome_dev,
                                        "descricao": f"Convertido de compra no cartão: {t['descricao']}",
                                        "valor": valor_total_conv,
                                        "pago": False,
                                        "conta_origem": conta_saida_conv,
                                        "forma_recebimento": "",
                                        "conta_destino": ""
                                    })
                                    salvar_dados_usuario(usuario_atual, dados)
                                    del st.session_state[conv_key]
                                    st.success(f"Convertido! A fatura do cartão foi reduzida em R$ {valor_total_conv:,.2f} e {nome_dev} agora te deve isso como empréstimo direto.")
                                    st.rerun()
                                if col_conv_nao.button("Cancelar", key=f"canc_{conv_key}"):
                                    del st.session_state[conv_key]
                                    st.rerun()

                            if st.session_state.get(del_key):
                                st.warning(f"Excluir '{t['descricao']}' (R$ {t['valor']:,.2f})?")
                                motivo_del = st.radio(
                                    "Motivo:",
                                    ["Foi um erro de lançamento (estornar da fatura)", "Estou perdoando a dívida (a fatura já foi cobrada, manter como está)"],
                                    key=f"motivo_{del_key}"
                                )
                                col_del_sim, col_del_nao = st.columns(2)
                                if col_del_sim.button("Confirmar exclusão", key=f"conf_{del_key}"):
                                    if motivo_del.startswith("Foi um erro"):
                                        alterar_fatura(dados, t.get("cartao_nome", ""), t["valor"], "subtrair", data=t["data"])
                                    dados["gastos_terceiros_cartao"].pop(idx_terc)
                                    salvar_dados_usuario(usuario_atual, dados)
                                    del st.session_state[del_key]
                                    st.success("Lançamento excluído.")
                                    st.rerun()
                                if col_del_nao.button("Cancelar", key=f"cancdel_{del_key}"):
                                    del st.session_state[del_key]
                                    st.rerun()
                            
                    # Mostrar Detalhamento do Empréstimo
                    if debitos_emp:
                        st.markdown("**💸 Detalhamento de Empréstimos (Dinheiro/Pix):**")
                        for idx_emp, e in enumerate(dados["gastos_terceiros_emprestimo"]):
                            if e not in debitos_emp:
                                continue
                            col_emp_txt, col_emp_btn = st.columns([4, 1])
                            col_emp_txt.write(f"- **{formatar_data_br(e['data'])}**: {e['descricao']} — **R$ {e['valor']:,.2f}** *(Retirado de: {e.get('conta_origem', 'Dinheiro')})*")

                            del_key_emp = f"delemp_{idx_emp}"
                            if col_emp_btn.button("🗑️", key=f"btn_{del_key_emp}", help="Excluir este empréstimo (erro ou dívida perdoada)"):
                                st.session_state[del_key_emp] = True

                            if st.session_state.get(del_key_emp):
                                st.warning(f"Excluir empréstimo '{e['descricao']}' (R$ {e['valor']:,.2f})?")
                                motivo_del_emp = st.radio(
                                    "Motivo:",
                                    ["Foi um erro de lançamento (devolver o valor para minha conta)", "Estou perdoando a dívida (o dinheiro já foi entregue, não devolver)"],
                                    key=f"motivo_{del_key_emp}"
                                )
                                col_del_sim_e, col_del_nao_e = st.columns(2)
                                if col_del_sim_e.button("Confirmar exclusão", key=f"conf_{del_key_emp}"):
                                    if motivo_del_emp.startswith("Foi um erro"):
                                        alterar_saldo(dados, e.get("conta_origem", ""), e["valor"], "somar")
                                    dados["gastos_terceiros_emprestimo"].pop(idx_emp)
                                    salvar_dados_usuario(usuario_atual, dados)
                                    del st.session_state[del_key_emp]
                                    st.success("Empréstimo excluído.")
                                    st.rerun()
                                if col_del_nao_e.button("Cancelar", key=f"cancdel_{del_key_emp}"):
                                    del st.session_state[del_key_emp]
                                    st.rerun()

                    # Mostrar Detalhamento dos Recorrentes de Terceiros
                    if debitos_rec_terc:
                        st.markdown("**🔁 Detalhamento de Recorrentes:**")
                        for rec_t in debitos_rec_terc:
                            valor_mes_rt = rec_t["valores_override"].get(periodo_ativo, rec_t["valor"])
                            pago_mes_rt = rec_t["pagamentos"].get(periodo_ativo, False)

                            col_rt1, col_rt2 = st.columns([3, 1])
                            col_rt1.write(f"- **{rec_t['descricao']}** 🔁 — **R$ {valor_mes_rt:,.2f}** *({rec_t.get('cartao_nome', 'Cartão Nu')})*")
                            novo_pago_rt = col_rt2.checkbox("Pago", value=pago_mes_rt, key=f"rt_pago_{rec_t['id']}_{periodo_ativo}")

                            if novo_pago_rt != pago_mes_rt:
                                if novo_pago_rt:
                                    alterar_fatura(dados, rec_t.get("cartao_nome", ""), valor_mes_rt, "somar", data=f"{periodo_ativo}-01")
                                else:
                                    alterar_fatura(dados, rec_t.get("cartao_nome", ""), valor_mes_rt, "subtrair", data=f"{periodo_ativo}-01")
                                rec_t["pagamentos"][periodo_ativo] = novo_pago_rt
                                salvar_dados_usuario(usuario_atual, dados)
                                st.rerun()

                            with st.expander(f"⚙️ Gerenciar '{rec_t['descricao']}' (recorrente)"):
                                novo_valor_rt = st.number_input(
                                    f"Valor de {mes_selecionado}/{ano_selecionado}:", min_value=0.0,
                                    value=float(valor_mes_rt), step=5.0, format="%.2f", key=f"editval_rt_{rec_t['id']}"
                                )
                                if st.button("Salvar novo valor deste mês", key=f"btn_editval_rt_{rec_t['id']}"):
                                    rec_t["valores_override"][periodo_ativo] = novo_valor_rt
                                    salvar_dados_usuario(usuario_atual, dados)
                                    st.rerun()
                                st.markdown("---")
                                if st.button(f"🛑 Encerrar a partir de {mes_selecionado}/{ano_selecionado}", key=f"encerrar_rt_{rec_t['id']}"):
                                    rec_t["fim"] = periodo_ativo
                                    salvar_dados_usuario(usuario_atual, dados)
                                    st.success("Recorrência encerrada a partir deste mês.")
                                    st.rerun()
                                st.markdown("---")
                                confirma_del_rt = st.checkbox("Confirmo que quero excluir esta recorrência por completo", key=f"chk_del_rt_{rec_t['id']}")
                                if st.button("🗑️ Excluir recorrência por completo", key=f"del_rt_{rec_t['id']}", disabled=not confirma_del_rt):
                                    dados["terceiros_recorrentes"] = [r for r in dados["terceiros_recorrentes"] if r["id"] != rec_t["id"]]
                                    salvar_dados_usuario(usuario_atual, dados)
                                    st.rerun()
                            
                    st.markdown("---")
                    st.markdown(f"**📥 Registrar Recebimento / Quitação de {nome_dev}**")
                    
                    # Criar opções para quitação parcial ou total de itens individuais
                    opcoes_debitos = []
                    for idx, t in enumerate(dados.get("gastos_terceiros_cartao", [])):
                        if not t["pago"] and t["nome"].lower() == nome_dev.lower():
                            opcoes_debitos.append({
                                "label": f"💳 Cartão: {t['descricao']} (R$ {t['valor']:,.2f})",
                                "tipo": "cartao",
                                "index": idx,
                                "valor": t["valor"],
                                "descricao": t["descricao"]
                            })
                    for idx, e in enumerate(dados.get("gastos_terceiros_emprestimo", [])):
                        if not e["pago"] and e["nome"].lower() == nome_dev.lower():
                            opcoes_debitos.append({
                                "label": f"💸 Empréstimo: {e['descricao']} (R$ {e['valor']:,.2f})",
                                "tipo": "emprestimo",
                                "index": idx,
                                "valor": e["valor"],
                                "descricao": e["descricao"]
                            })
                            
                    if opcoes_debitos:
                        item_labels = [opt["label"] for opt in opcoes_debitos]
                        item_sel_label = st.selectbox(f"Selecione qual item foi pago:", item_labels, key=f"sel_quitar_{nome_dev}")
                        
                        selected_opt = next(opt for opt in opcoes_debitos if opt["label"] == item_sel_label)
                        
                        with st.form(f"form_receber_pessoa_{nome_dev}_{selected_opt['tipo']}_{selected_opt['index']}", clear_on_submit=True):
                            st.write(f"**Valor Original Pendente:** R$ {selected_opt['valor']:,.2f}")
                            valor_pago = st.number_input("Quanto a pessoa pagou de fato? (R$):", min_value=0.0, value=selected_opt["valor"], step=10.0, format="%.2f", key=f"pago_val_{nome_dev}")
                            
                            # Conta que vai receber o dinheiro
                            conta_dest_reemb = st.selectbox("Depositar na Conta / Banco:", [c["nome"] for c in dados["contas"]], key=f"cont_dest_{nome_dev}")
                            forma_rec = st.selectbox("Forma de Pagamento:", ["PIX", "Dinheiro", "Transferência"], key=f"form_rec_{nome_dev}")
                            
                            confirmar_rec = st.form_submit_button("Confirmar Pagamento 📥")
                            if confirmar_rec:
                                tipo_item = selected_opt["tipo"]
                                idx_orig = selected_opt["index"]
                                valor_original = selected_opt["valor"]
                                
                                if valor_pago <= 0:
                                    st.error("O valor pago deve ser maior que zero!")
                                else:
                                    if tipo_item == "cartao":
                                        item_db = dados["gastos_terceiros_cartao"][idx_orig]
                                    else:
                                        item_db = dados["gastos_terceiros_emprestimo"][idx_orig]
                                        
                                    # CASO 1: PAGAMENTO INTEGRAL (EXATO)
                                    if abs(valor_pago - valor_original) < 0.01:
                                        item_db["pago"] = True
                                        item_db["conta_destino"] = conta_dest_reemb
                                        item_db["data_pagamento"] = str(datetime.now().date())
                                        if tipo_item == "emprestimo":
                                            item_db["forma_recebimento"] = forma_rec

                                        dados.setdefault("recebimentos_terceiros", []).append({
                                            "data": str(datetime.now().date()),
                                            "nome": nome_dev,
                                            "descricao": selected_opt["descricao"],
                                            "valor": valor_pago,
                                            "conta_destino": conta_dest_reemb
                                        })
                                        alterar_saldo(dados, conta_dest_reemb, valor_pago, "somar")
                                        salvar_dados_usuario(usuario_atual, dados)
                                        st.success(f"Quitação total realizada! R$ {valor_pago:,.2f} adicionados à conta '{conta_dest_reemb}'.")
                                        st.rerun()
                                        
                                    # CASO 2: PAGOU A MENOS (PAGAMENTO PARCIAL)
                                    elif valor_pago < valor_original:
                                        novo_valor_pendente = valor_original - valor_pago
                                        item_db["valor"] = novo_valor_pendente
                                        item_db["descricao"] = f"{item_db['descricao']} (Parcial R$ {valor_pago:,.2f} recebido)"

                                        dados.setdefault("recebimentos_terceiros", []).append({
                                            "data": str(datetime.now().date()),
                                            "nome": nome_dev,
                                            "descricao": selected_opt["descricao"],
                                            "valor": valor_pago,
                                            "conta_destino": conta_dest_reemb
                                        })
                                        alterar_saldo(dados, conta_dest_reemb, valor_pago, "somar")
                                        salvar_dados_usuario(usuario_atual, dados)
                                        st.success(f"Reembolso parcial! {nome_dev} pagou R$ {valor_pago:,.2f} e ainda restam R$ {novo_valor_pendente:,.2f} pendentes neste item.")
                                        st.rerun()
                                        
                                    # CASO 3: PAGOU A MAIS (SOBROU TROCO / EXCESSO)
                                    elif valor_pago > valor_original:
                                        item_db["pago"] = True
                                        item_db["conta_destino"] = conta_dest_reemb
                                        item_db["data_pagamento"] = str(datetime.now().date())
                                        if tipo_item == "emprestimo":
                                            item_db["forma_recebimento"] = forma_rec
                                            
                                        excesso = valor_pago - valor_original

                                        # Registra a parte "base" da dívida como recebimento de terceiro;
                                        # o excesso é lançado à parte como Receita (evita duplicar no extrato)
                                        dados.setdefault("recebimentos_terceiros", []).append({
                                            "data": str(datetime.now().date()),
                                            "nome": nome_dev,
                                            "descricao": selected_opt["descricao"],
                                            "valor": valor_original,
                                            "conta_destino": conta_dest_reemb
                                        })
                                        
                                        # Deposita valor total na conta
                                        alterar_saldo(dados, conta_dest_reemb, valor_pago, "somar")
                                        
                                        # Lança excesso como Receita
                                        nova_rec = {
                                            "data": str(datetime.now().date()),
                                            "descricao": f"Diferença paga a mais por {nome_dev} (Ref: {selected_opt['descricao']})",
                                            "valor": excesso,
                                            "conta": conta_dest_reemb
                                        }
                                        dados.setdefault("receitas", []).append(nova_rec)
                                        
                                        salvar_dados_usuario(usuario_atual, dados)
                                        st.success(f"Quitação total e Excesso registrado! Como o pagamento foi R$ {valor_pago:,.2f} (R$ {excesso:,.2f} a mais que a dívida), a diferença entrou como Receita e o saldo total foi para a conta '{conta_dest_reemb}'.")
                                        st.rerun()

    # SUB-ABA 5.3: HISTÓRICO DE REEMBOLSOS RECEBIDOS
    with sub_abas_terceiros[2]:
        st.markdown(f"**Pagamentos e Reembolsos Recebidos em {mes_selecionado}/{ano_selecionado}**")
        st.caption("Cada reembolso aparece apenas no mês em que foi efetivamente pago — não fica repetido nos meses seguintes.")

        def data_pagamento_de(item):
            return item.get("data_pagamento", item["data"])

        pessoa_cartao_paga_mes = [
            t for t in dados.get("gastos_terceiros_cartao", [])
            if t["pago"] and str(data_pagamento_de(t))[:7] == periodo_ativo
        ]
        pessoa_emprestimo_pago_mes = [
            e for e in dados.get("gastos_terceiros_emprestimo", [])
            if e["pago"] and str(data_pagamento_de(e))[:7] == periodo_ativo
        ]

        if not pessoa_cartao_paga_mes and not pessoa_emprestimo_pago_mes:
            st.info("Nenhum reembolso recebido neste mês.")
        else:
            if pessoa_cartao_paga_mes:
                st.markdown("**💳 Compras no Cartão (Pagas/Reembolsadas):**")
                for idx_hc, t in enumerate(dados["gastos_terceiros_cartao"]):
                    if t not in pessoa_cartao_paga_mes:
                        continue
                    col_hc1, col_hc2 = st.columns([4, 1])
                    col_hc1.write(f"- **{formatar_data_br(data_pagamento_de(t))}**: {t['nome']} pagou: **R$ {t['valor']:,.2f}** - *({t['descricao']})*")
                    del_hc_key = f"delhist_c_{idx_hc}"
                    if col_hc2.button("🗑️", key=f"btn_{del_hc_key}"):
                        st.session_state[del_hc_key] = True
                    if st.session_state.get(del_hc_key):
                        st.warning("Excluir este registro do histórico? (não mexe no saldo, só remove da lista)")
                        c_s, c_n = st.columns(2)
                        if c_s.button("Confirmar exclusão", key=f"conf_{del_hc_key}"):
                            dados["gastos_terceiros_cartao"].pop(idx_hc)
                            salvar_dados_usuario(usuario_atual, dados)
                            del st.session_state[del_hc_key]
                            st.rerun()
                        if c_n.button("Cancelar", key=f"canc_{del_hc_key}"):
                            del st.session_state[del_hc_key]
                            st.rerun()

            if pessoa_emprestimo_pago_mes:
                st.markdown("**💸 Empréstimos (Quitados/Recebidos):**")
                for idx_he, e in enumerate(dados["gastos_terceiros_emprestimo"]):
                    if e not in pessoa_emprestimo_pago_mes:
                        continue
                    col_he1, col_he2 = st.columns([4, 1])
                    col_he1.write(f"- **{formatar_data_br(data_pagamento_de(e))}**: {e['nome']} quitou: **R$ {e['valor']:,.2f}** - *({e['descricao']})* -> Destino: {e.get('conta_destino', 'Nu')} ({e.get('forma_recebimento', 'PIX')})")
                    del_he_key = f"delhist_e_{idx_he}"
                    if col_he2.button("🗑️", key=f"btn_{del_he_key}"):
                        st.session_state[del_he_key] = True
                    if st.session_state.get(del_he_key):
                        st.warning("Excluir este registro do histórico? (não mexe no saldo, só remove da lista)")
                        c_s, c_n = st.columns(2)
                        if c_s.button("Confirmar exclusão", key=f"conf_{del_he_key}"):
                            dados["gastos_terceiros_emprestimo"].pop(idx_he)
                            salvar_dados_usuario(usuario_atual, dados)
                            del st.session_state[del_he_key]
                            st.rerun()
                        if c_n.button("Cancelar", key=f"canc_{del_he_key}"):
                            del st.session_state[del_he_key]
                            st.rerun()

        # --- RELATÓRIO SIMPLES POR DEVEDOR (visão geral, não limitado ao mês) ---
        st.markdown("---")
        st.markdown("### 📋 Relatório por Devedor")
        st.caption("Resumo geral de cada pessoa: quanto já foi pago (histórico completo) e quanto ainda falta. Você pode limpar o histórico pago de uma pessoa para não acumular registros antigos.")

        todos_nomes = sorted(set(
            [t["nome"] for t in dados.get("gastos_terceiros_cartao", [])] +
            [e["nome"] for e in dados.get("gastos_terceiros_emprestimo", [])]
        ))

        if not todos_nomes:
            st.info("Nenhum devedor cadastrado ainda.")
        else:
            for nome_rel in todos_nomes:
                cartao_pessoa = [t for t in dados.get("gastos_terceiros_cartao", []) if t["nome"].lower() == nome_rel.lower()]
                emp_pessoa = [e for e in dados.get("gastos_terceiros_emprestimo", []) if e["nome"].lower() == nome_rel.lower()]

                total_pago_pessoa = sum(t["valor"] for t in cartao_pessoa if t["pago"]) + sum(e["valor"] for e in emp_pessoa if e["pago"])
                total_pendente_pessoa = sum(t["valor"] for t in cartao_pessoa if not t["pago"]) + sum(e["valor"] for e in emp_pessoa if not e["pago"])
                qtd_pagos_pessoa = len([t for t in cartao_pessoa if t["pago"]]) + len([e for e in emp_pessoa if e["pago"]])

                with st.expander(f"👤 {nome_rel} — Pago: R$ {total_pago_pessoa:,.2f} | Falta: R$ {total_pendente_pessoa:,.2f}"):
                    col_rel1, col_rel2 = st.columns(2)
                    col_rel1.metric("✅ Já pago (histórico)", f"R$ {total_pago_pessoa:,.2f}")
                    col_rel2.metric("⏳ Ainda falta", f"R$ {total_pendente_pessoa:,.2f}")

                    if qtd_pagos_pessoa > 0:
                        st.markdown("---")
                        confirma_limpa_pessoa = st.checkbox(
                            f"Confirmo que quero apagar os {qtd_pagos_pessoa} registro(s) já pagos de {nome_rel} (o que ainda falta não é afetado)",
                            key=f"chk_limpa_hist_{nome_rel}"
                        )
                        if st.button(f"🗑️ Limpar histórico pago de {nome_rel}", key=f"limpa_hist_{nome_rel}", disabled=not confirma_limpa_pessoa):
                            dados["gastos_terceiros_cartao"] = [t for t in dados["gastos_terceiros_cartao"] if not (t["nome"].lower() == nome_rel.lower() and t["pago"])]
                            dados["gastos_terceiros_emprestimo"] = [e for e in dados["gastos_terceiros_emprestimo"] if not (e["nome"].lower() == nome_rel.lower() and e["pago"])]
                            salvar_dados_usuario(usuario_atual, dados)
                            st.success(f"Histórico pago de {nome_rel} foi limpo.")
                            st.rerun()

# ----------------- ABA 5: NOVA ABA SALDOS (CONTAS DINÂMICAS & FATURAS DE CARTÃO) -----------------
with abas[4]:
    st.markdown("<h3 class='titulo-secao'>💳 Gestão de Contas, Saldos & Cartões</h3>", unsafe_allow_html=True)
    st.caption("Crie, edite e acompanhe seus saldos bancários e faturas de cartões de crédito.")
    
    # 1. Visualizar Saldos do Mês Selecionado (baseado nas datas dos lançamentos, não no saldo "de hoje")
    st.markdown(f"#### Seus Saldos em {mes_selecionado}/{ano_selecionado}")
    st.caption("Cada mês mostra o saldo que a conta tinha NAQUELE mês — um ganho lançado em setembro não aparece em agosto.")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("**Contas Correntes (Dia a Dia):**")
        for conta in dados["contas"]:
            if conta.get("tipo", "Normal") == "Normal":
                saldo_mes_conta = calcular_saldo_conta_no_periodo(dados, conta["nome"], periodo_ativo)
                st.info(f"🏦 **{conta['nome']}:** R$ {saldo_mes_conta:,.2f}")
    with col_c2:
        st.markdown("**Poupança & Guardados:**")
        for conta in dados["contas"]:
            if conta.get("tipo", "Normal") == "Guardado":
                saldo_mes_conta = calcular_saldo_conta_no_periodo(dados, conta["nome"], periodo_ativo)
                st.success(f"🔒 **{conta['nome']}:** R$ {saldo_mes_conta:,.2f}")

    with st.expander("🔎 Ver saldo real de HOJE (para fazer transferências, pagamentos, etc.)"):
        st.caption("Este é o valor real disponível agora, independente do mês selecionado acima — use-o para saber quanto você realmente tem disponível hoje.")
        for conta in dados["contas"]:
            icone_hoje = "🔒" if conta.get("tipo") == "Guardado" else "🏦"
            st.write(f"{icone_hoje} **{conta['nome']}:** R$ {conta['saldo']:,.2f}")
                
    st.markdown(f"#### Faturas de Cartões de Crédito em {mes_selecionado}/{ano_selecionado}")
    st.caption("Cada mês mostra a fatura que existia NAQUELE mês — uma fatura de junho não aparece como aberta em maio.")
    col_cart_s = st.columns(2)
    for c_idx, cartao in enumerate(dados.get("cartoes", [])):
        fatura_no_mes = calcular_fatura_cartao_no_periodo(dados, cartao["nome"], periodo_ativo)
        with col_cart_s[c_idx % 2]:
            st.error(f"💳 **{cartao['nome']}:** R$ {fatura_no_mes:,.2f}\n\n*Fecha dia {cartao.get('fechamento', 1)} • Vence dia {cartao.get('vencimento', 10)}*")

    with st.expander("🔎 Ver fatura real de HOJE (para pagar de verdade)"):
        st.caption("Este é o valor real da fatura agora, independente do mês selecionado acima.")
        for cartao in dados.get("cartoes", []):
            st.write(f"💳 **{cartao['nome']}:** R$ {cartao['fatura']:,.2f}")

    st.markdown("---")
    st.markdown(f"#### 📒 Extrato de {mes_selecionado}/{ano_selecionado}")
    st.caption("Saldo anterior (fim do mês passado) → movimentação do mês → saldo no fim do mês selecionado, conta por conta.")
    periodo_anterior_ativo = periodo_anterior(periodo_ativo)
    for conta in dados["contas"]:
        saldo_anterior_periodo = calcular_saldo_conta_no_periodo(dados, conta["nome"], periodo_anterior_ativo)
        saldo_final_periodo = calcular_saldo_conta_no_periodo(dados, conta["nome"], periodo_ativo)
        movimentacao = saldo_final_periodo - saldo_anterior_periodo
        icone_conta = "🔒" if conta.get("tipo") == "Guardado" else "🏦"
        col_ext1, col_ext2, col_ext3 = st.columns(3)
        col_ext1.metric(f"{icone_conta} {conta['nome']} — Saldo Anterior", f"R$ {saldo_anterior_periodo:,.2f}")
        col_ext2.metric("Movimentação no Mês", f"R$ {movimentacao:,.2f}")
        col_ext3.metric("Saldo no Fim do Mês", f"R$ {saldo_final_periodo:,.2f}")

    st.markdown("#### 📒 Extrato de Fatura de Cartões")
    for cartao in dados.get("cartoes", []):
        fatura_anterior_periodo = calcular_fatura_cartao_no_periodo(dados, cartao["nome"], periodo_anterior_ativo)
        fatura_final_periodo = calcular_fatura_cartao_no_periodo(dados, cartao["nome"], periodo_ativo)
        movimentacao_fat = fatura_final_periodo - fatura_anterior_periodo
        col_extf1, col_extf2, col_extf3 = st.columns(3)
        col_extf1.metric(f"💳 {cartao['nome']} — Fatura Anterior", f"R$ {fatura_anterior_periodo:,.2f}")
        col_extf2.metric("Movimentação no Mês", f"R$ {movimentacao_fat:,.2f}")
        col_extf3.metric("Fatura no Fim do Mês", f"R$ {fatura_final_periodo:,.2f}")
                
    st.markdown("---")
    
    # Seções expansíveis para gerenciamento
    aba_ger_conta = st.tabs(["💸 Transferir", "💳 Pagar Fatura", "➕ Criar Conta/Cartão", "⚙️ Renomear/Excluir"])
    
    # 6.1 Lançamentos entre Contas (Transferências)
    with aba_ger_conta[0]:
        st.markdown("**Fazer Transferência entre Contas Bancárias**")
        with st.form("form_transferencia", clear_on_submit=True):
            contas_nomes = [c["nome"] for c in dados["contas"]]
            origem = st.selectbox("Conta de Origem (Sai o dinheiro):", contas_nomes)
            destino = st.selectbox("Conta de Destino (Entra o dinheiro):", contas_nomes)
            valor_transf = st.number_input("Valor da Transferência (R$)", min_value=0.0, step=50.0, format="%.2f")
            
            confirmar = st.form_submit_button("Realizar Transferência 🔁")
            if confirmar:
                if origem == destino:
                    st.error("A conta de origem não pode ser igual à conta de destino!")
                elif valor_transf <= 0:
                    st.error("O valor deve ser maior do que zero!")
                else:
                    if alterar_saldo(dados, origem, valor_transf, "subtrair"):
                        alterar_saldo(dados, destino, valor_transf, "somar")
                        
                        # Salva registro no histórico de transferências
                        nova_transf = {
                            "data": str(datetime.now().date()),
                            "origem": origem,
                            "destino": destino,
                            "valor": valor_transf
                        }
                        dados.setdefault("transferencias", []).append(nova_transf)
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success(f"Transferência de R$ {valor_transf:,.2f} realizada com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao realizar transferência.")

    # 6.2 PAGAR FATURA DO CARTÃO DE CRÉDITO
    with aba_ger_conta[1]:
        st.markdown("**Pagar Fatura de Cartão de Crédito**")
        st.caption("Efetua o pagamento do saldo do cartão, reduzindo a fatura e retirando o dinheiro da sua conta bancária corrente.")
        
        with st.form("form_pagar_fatura", clear_on_submit=True):
            cartao_a_pagar = st.selectbox("Escolha qual Cartão quer pagar:", [c["nome"] for c in dados["cartoes"]])
            conta_pagadora = st.selectbox("Pagar usando o Saldo de qual Conta:", [c["nome"] for c in dados["contas"] if c["tipo"] == "Normal"])
            
            fatura_atual_val = next((c["fatura"] for c in dados["cartoes"] if c["nome"] == cartao_a_pagar), 0.0)
            st.write(f"Fatura total pendente deste cartão: **R$ {fatura_atual_val:,.2f}**")
            
            valor_pagamento_fat = st.number_input("Valor a pagar (R$):", min_value=0.0, value=fatura_atual_val, step=10.0, format="%.2f")
            
            pagar_fat_btn = st.form_submit_button("Confirmar Pagamento de Fatura 💳")
            if pagar_fat_btn and valor_pagamento_fat > 0:
                # Retirar do saldo da conta
                if alterar_saldo(dados, conta_pagadora, valor_pagamento_fat, "subtrair"):
                    # Reduzir fatura do cartão
                    alterar_fatura(dados, cartao_a_pagar, valor_pagamento_fat, "subtrair")
                    
                    # Salva nas transferências para registro histórico
                    dados.setdefault("transferencias", []).append({
                        "data": str(datetime.now().date()),
                        "origem": conta_pagadora,
                        "destino": f"Fatura {cartao_a_pagar}",
                        "valor": valor_pagamento_fat
                    })
                    salvar_dados_usuario(usuario_atual, dados)
                    st.success(f"Fatura do '{cartao_a_pagar}' no valor de R$ {valor_pagamento_fat:,.2f} foi paga usando a conta '{conta_pagadora}'!")
                    st.rerun()

    # 6.3 CRIAR CONTAS OU CARTÕES DINÂMICOS
    with aba_ger_conta[2]:
        col_c_c1, col_c_c2 = st.columns(2)
        
        with col_c_c1:
            st.markdown("**🏦 Criar Nova Conta Bancária**")
            with st.form("form_criar_conta_din", clear_on_submit=True):
                nome_nova_conta = st.text_input("Nome da Conta (Ex: Inter, Caixa, Carteira):")
                tipo_nova_conta = st.selectbox("Tipo da Conta:", ["Normal", "Guardado"])
                saldo_inicial = st.number_input("Saldo Inicial (R$):", min_value=0.0, step=10.0, format="%.2f")
                criar = st.form_submit_button("Criar Conta 🏦")
                if criar and nome_nova_conta:
                    ja_existe = any(c["nome"].lower() == nome_nova_conta.lower() for c in dados["contas"])
                    if ja_existe:
                        st.error("Já existe uma conta cadastrada com esse nome!")
                    else:
                        dados["contas"].append({
                            "nome": nome_nova_conta.strip(),
                            "saldo": saldo_inicial,
                            "tipo": tipo_nova_conta
                        })
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success(f"Conta '{nome_nova_conta}' criada com sucesso!")
                        st.rerun()
                        
        with col_c_c2:
            st.markdown("**💳 Criar Novo Cartão de Crédito**")
            with st.form("form_criar_cartao_din", clear_on_submit=True):
                nome_novo_cartao = st.text_input("Nome do Cartão (Ex: Cartão Inter, Cartão Elo):")
                fatura_inicial = st.number_input("Fatura Inicial Pendente (R$):", min_value=0.0, step=10.0, format="%.2f")
                col_fech, col_venc = st.columns(2)
                dia_fechamento_novo = col_fech.number_input("Dia do Fechamento:", min_value=1, max_value=28, value=1, step=1)
                dia_vencimento_novo = col_venc.number_input("Dia do Vencimento:", min_value=1, max_value=28, value=10, step=1)
                st.caption("Compras feitas no dia do fechamento (ou depois) entram automaticamente na fatura do mês seguinte.")
                criar_c = st.form_submit_button("Criar Cartão 💳")
                if criar_c and nome_novo_cartao:
                    ja_existe = any(c["nome"].lower() == nome_novo_cartao.lower() for c in dados["cartoes"])
                    if ja_existe:
                        st.error("Já existe um cartão cadastrado com esse nome!")
                    else:
                        dados["cartoes"].append({
                            "nome": nome_novo_cartao.strip(),
                            "fatura": fatura_inicial,
                            "fechamento": int(dia_fechamento_novo),
                            "vencimento": int(dia_vencimento_novo)
                        })
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success(f"Cartão '{nome_novo_cartao}' criado com sucesso!")
                        st.rerun()

    # 6.4 RENOMEAR OU EXCLUIR CONTAS / CARTÕES
    with aba_ger_conta[3]:
        st.markdown("**Renomear ou Excluir uma Conta ou Cartão**")
        tipo_ger = st.radio("Selecione qual deseja gerenciar:", ["Contas Bancárias", "Cartões de Crédito"], horizontal=True)
        
        if tipo_ger == "Contas Bancárias":
            conta_selecionada = st.selectbox("Selecione a Conta bancária para alterar:", [c["nome"] for c in dados["contas"]])
            col_ren, col_exc = st.columns(2)
            
            with col_ren:
                st.markdown("**Renomear Conta:**")
                novo_nome_conta = st.text_input("Novo Nome da Conta:", value=conta_selecionada)
                if st.button("Salvar Novo Nome"):
                    if novo_nome_conta and novo_nome_conta != conta_selecionada:
                        for c in dados["contas"]:
                            if c["nome"] == conta_selecionada:
                                c["nome"] = novo_nome_conta.strip()
                        # update other lists
                        for r in dados.get("receitas", []):
                            if r.get("conta") == conta_selecionada: r["conta"] = novo_nome_conta
                        for g in dados.get("gastos_fixos", []):
                            if g.get("conta") == conta_selecionada: g["conta"] = novo_nome_conta
                        for a in dados.get("gastos_avulsos", []):
                            if a.get("conta") == conta_selecionada: a["conta"] = novo_nome_conta
                        for e in dados.get("gastos_terceiros_emprestimo", []):
                            if e.get("conta_origem") == conta_selecionada: e["conta_origem"] = novo_nome_conta
                            if e.get("conta_destino") == conta_selecionada: e["conta_destino"] = novo_nome_conta
                        for t in dados.get("transferencias", []):
                            if t.get("origem") == conta_selecionada: t["origem"] = novo_nome_conta
                            if t.get("destino") == conta_selecionada: t["destino"] = novo_nome_conta
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success("Conta renomeada!")
                        st.rerun()
            with col_exc:
                st.markdown("**Excluir Conta:**")
                st.warning("⚠️ Ao excluir a conta, seu saldo ativo será perdido.")
                confirma_exc_conta = st.checkbox(f"Confirmo que quero excluir '{conta_selecionada}'", key="chk_exc_conta")
                if st.button("Confirmar Exclusão ❌", disabled=not confirma_exc_conta):
                    if len(dados["contas"]) <= 1:
                        st.error("Você deve manter pelo menos uma conta ativa!")
                    else:
                        dados["contas"] = [c for c in dados["contas"] if c["nome"] != conta_selecionada]
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success("Conta excluída!")
                        st.rerun()
                        
        else: # Cartões de Crédito
            cartao_selecionado = st.selectbox("Selecione o Cartão para gerenciar:", [c["nome"] for c in dados["cartoes"]])
            cartao_obj_sel = obter_dados_cartao(dados, cartao_selecionado)

            st.markdown("**Datas de Fechamento e Vencimento:**")
            col_fech_e, col_venc_e = st.columns(2)
            novo_fech = col_fech_e.number_input("Dia do Fechamento:", min_value=1, max_value=28, value=cartao_obj_sel.get("fechamento", 1), step=1, key="edit_fech")
            novo_venc = col_venc_e.number_input("Dia do Vencimento:", min_value=1, max_value=28, value=cartao_obj_sel.get("vencimento", 10), step=1, key="edit_venc")
            if st.button("Salvar Datas de Fatura"):
                cartao_obj_sel["fechamento"] = int(novo_fech)
                cartao_obj_sel["vencimento"] = int(novo_venc)
                salvar_dados_usuario(usuario_atual, dados)
                st.success("Datas de fechamento/vencimento atualizadas!")
                st.rerun()
            st.markdown("---")

            with st.expander("🛠️ Corrigir valor da fatura manualmente"):
                st.caption(
                    "Use isso só se a fatura ficou com um valor errado por causa de algum bug "
                    "(por exemplo, um lançamento excluído que não estornou direito). Isso muda "
                    "diretamente o valor da fatura, sem mexer no saldo de nenhuma conta."
                )
                novo_valor_fatura = st.number_input(
                    "Valor correto da fatura:", min_value=0.0,
                    value=float(cartao_obj_sel.get("fatura", 0.0)), step=1.0, format="%.2f",
                    key="corrigir_fatura_valor"
                )
                if st.button("Aplicar correção na fatura", key="btn_corrigir_fatura"):
                    diff_correcao = novo_valor_fatura - cartao_obj_sel.get("fatura", 0.0)
                    if diff_correcao != 0:
                        alterar_fatura(dados, cartao_selecionado, abs(diff_correcao), "somar" if diff_correcao > 0 else "subtrair")
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success(f"Fatura corrigida para R$ {novo_valor_fatura:,.2f}!")
                        st.rerun()
                    else:
                        st.info("O valor já está igual, nada para corrigir.")
            st.markdown("---")

            col_ren_c, col_exc_c = st.columns(2)
            
            with col_ren_c:
                st.markdown("**Renomear Cartão:**")
                novo_nome_cartao = st.text_input("Novo Nome do Cartão:", value=cartao_selecionado)
                if st.button("Salvar Novo Nome de Cartão"):
                    if novo_nome_cartao and novo_nome_cartao != cartao_selecionado:
                        for c in dados["cartoes"]:
                            if c["nome"] == cartao_selecionado:
                                c["nome"] = novo_nome_cartao.strip()
                        for g in dados.get("gastos_fixos", []):
                            if g.get("cartao_nome") == cartao_selecionado: g["cartao_nome"] = novo_nome_cartao
                        for a in dados.get("gastos_avulsos", []):
                            if a.get("cartao_nome") == cartao_selecionado: a["cartao_nome"] = novo_nome_cartao
                        for t in dados.get("gastos_terceiros_cartao", []):
                            if t.get("cartao_nome") == cartao_selecionado: t["cartao_nome"] = novo_nome_cartao
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success("Cartão renomeado!")
                        st.rerun()
            with col_exc_c:
                st.markdown("**Excluir Cartão:**")
                st.warning("⚠️ Ao excluir o cartão, seu saldo de fatura ativa será deletado.")
                confirma_exc_cartao = st.checkbox(f"Confirmo que quero excluir '{cartao_selecionado}'", key="chk_exc_cartao")
                if st.button("Confirmar Exclusão de Cartão ❌", disabled=not confirma_exc_cartao):
                    if len(dados["cartoes"]) <= 1:
                        st.error("Você deve manter pelo menos um cartão ativo!")
                    else:
                        dados["cartoes"] = [c for c in dados["cartoes"] if c["nome"] != cartao_selecionado]
                        salvar_dados_usuario(usuario_atual, dados)
                        st.success("Cartão excluído!")
                        st.rerun()

# ----------------- ABA 6: POUPANÇA (GUARDADO) -----------------
with abas[5]:
    st.markdown("<h3 class='titulo-secao'>🔒 Dinheiro Guardado & Poupança</h3>", unsafe_allow_html=True)
    st.markdown("""
    <div class="card-didatico">
        💡 <b>Como funciona seu Dinheiro Guardado:</b><br>
        Toda conta que você cria na aba anterior e define como do tipo <b>"Guardado"</b> (como o Banco Pan ou as Caixinhas) 
        é listada aqui de forma integrada! Para guardar dinheiro, basta ir na aba anterior e fazer uma transferência de uma conta corrente normal para a sua conta de poupança.
    </div>
    """, unsafe_allow_html=True)
    
    # Calcular e mostrar saldos de investimentos (referentes ao mês/ano selecionado no topo)
    contas_guardado = [c for c in dados["contas"] if c.get("tipo", "Normal") == "Guardado"]
    saldos_guardado_mes = {c["nome"]: calcular_saldo_conta_no_periodo(dados, c["nome"], periodo_ativo) for c in contas_guardado}
    total_reservas = sum(saldos_guardado_mes.values())

    st.caption(f"Valores referentes a {mes_selecionado}/{ano_selecionado}.")
    st.markdown("#### Detalhamento das Economias:")
    for conta in contas_guardado:
        st.info(f"💰 **{conta['nome']}:** R$ {saldos_guardado_mes[conta['nome']]:,.2f}")
        
    st.markdown(f"### 📈 Total Acumulado Guardado: **R$ {total_reservas:,.2f}**")

    if contas_guardado:
        st.markdown("#### 📒 Extrato do Mês por Conta Guardada")
        periodo_anterior_guardado = periodo_anterior(periodo_ativo)
        for conta in contas_guardado:
            saldo_ant_g = calcular_saldo_conta_no_periodo(dados, conta["nome"], periodo_anterior_guardado)
            saldo_fim_g = calcular_saldo_conta_no_periodo(dados, conta["nome"], periodo_ativo)
            movimentacao_g = saldo_fim_g - saldo_ant_g
            col_g1, col_g2, col_g3 = st.columns(3)
            col_g1.metric(f"🔒 {conta['nome']} — Anterior", f"R$ {saldo_ant_g:,.2f}")
            col_g2.metric("Movimentação no Mês", f"R$ {movimentacao_g:,.2f}")
            col_g3.metric("Saldo no Fim do Mês", f"R$ {saldo_fim_g:,.2f}")

        with st.expander("🔎 Ver saldo real de HOJE (independente do mês selecionado)"):
            for conta in contas_guardado:
                st.write(f"🔒 **{conta['nome']}:** R$ {conta['saldo']:,.2f}")

    # Gráfico de Pizza: composição das reservas guardadas
    if contas_guardado and total_reservas > 0:
        st.markdown("#### 🥧 Composição das suas Reservas")
        df_pizza_guardado = pd.DataFrame([{"Conta": nome, "Valor": v} for nome, v in saldos_guardado_mes.items() if v > 0])
        fig_guardado = px.pie(df_pizza_guardado, values="Valor", names="Conta", hole=0.4,
                               color_discrete_sequence=px.colors.sequential.Purples_r)
        fig_guardado.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color="#FFFFFF",
            margin=dict(t=10, b=10, l=10, r=10),
            height=260
        )
        st.plotly_chart(fig_guardado, use_container_width=True)
    
    # Histórico de transferências para poupança (economias)
    transferencias_poupanca = []
    for t in dados.get("transferencias", []):
        dest_tipo = next((c["tipo"] for c in dados["contas"] if c["nome"] == t["destino"]), "Normal")
        orig_tipo = next((c["tipo"] for c in dados["contas"] if c["nome"] == t["origem"]), "Normal")
        if dest_tipo == "Guardado" and orig_tipo == "Normal":
            transferencias_poupanca.append(t)
            
    if transferencias_poupanca:
        st.markdown("#### Histórico Recente de Economias Guardadas")
        df_dep = pd.DataFrame(transferencias_poupanca)
        df_dep = df_dep[["data", "origem", "destino", "valor"]]
        df_dep["data"] = df_dep["data"].apply(formatar_data_br)
        df_dep.columns = ["Data", "Origem", "Destino (Guardado)", "Valor Guardado (R$)"]
        st.dataframe(df_dep, use_container_width=True)

# ----------------- ABA 7: ALTERAÇÃO DE SENHA (PIN) -----------------
with abas[6]:
    st.markdown("<h3 class='titulo-secao'>⚙️ Alterar Sua Senha (PIN)</h3>", unsafe_allow_html=True)
    st.caption("Sua senha garante a privacidade dos seus dados financeiros se outras pessoas usarem o mesmo aplicativo.")
    
    with st.form("form_alterar_senha"):
        senha_atual = st.text_input("Digite o PIN atual (6 dígitos):", type="password", max_chars=6)
        nova_senha = st.text_input("Digite o NOVO PIN (6 dígitos numéricos):", type="password", max_chars=6)
        nova_senha_conf = st.text_input("Confirme o NOVO PIN (6 dígitos numéricos):", type="password", max_chars=6)
        
        atualizar_btn = st.form_submit_button("Alterar Senha")
        if atualizar_btn:
            if senha_atual != dados.get("pin", "123456"):
                st.error("PIN atual incorreto!")
            elif not nova_senha.isdigit() or len(nova_senha) != 6:
                st.error("O novo PIN deve conter exatamente 6 números.")
            elif nova_senha != nova_senha_conf:
                st.error("A confirmação da nova senha está diferente!")
            else:
                dados["pin"] = nova_senha
                salvar_dados_usuario(usuario_atual, dados)
                st.success("Sua senha (PIN) de 6 dígitos foi alterada com sucesso!")
                st.rerun()

    st.markdown("---")
    st.markdown("### 🔑 Pergunta de Segurança (Recuperação de PIN)")
    if dados.get("pergunta_seguranca"):
        st.caption(f"Pergunta atual: **{dados['pergunta_seguranca']}**")
    else:
        st.caption("Você ainda não configurou uma pergunta de segurança. Configure uma para poder recuperar seu PIN caso esqueça.")

    pergunta_escolhida_cfg = st.selectbox("Pergunta de Segurança:", PERGUNTAS_SEGURANCA_PADRAO, key="pergunta_cfg")
    pergunta_final_cfg = pergunta_escolhida_cfg
    if pergunta_escolhida_cfg == PERGUNTAS_SEGURANCA_PADRAO[-1]:
        pergunta_final_cfg = st.text_input("Digite sua pergunta personalizada:", key="pergunta_custom_cfg")
    resposta_cfg = st.text_input("Resposta:", key="resposta_cfg")
    if st.button("Salvar Pergunta de Segurança"):
        if pergunta_final_cfg and resposta_cfg:
            dados["pergunta_seguranca"] = pergunta_final_cfg
            dados["resposta_hash"] = hash_resposta(resposta_cfg)
            salvar_dados_usuario(usuario_atual, dados)
            st.success("Pergunta de segurança salva com sucesso!")
            st.rerun()
        else:
            st.error("Preencha a pergunta e a resposta.")
