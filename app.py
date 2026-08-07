# -*- coding: utf-8 -*-
"""
Painel de Controle — Nosferatu Diário de Leitura
Controle remoto: metas, desafios, íncubo surpresa, limites por usuário, bloqueios.
Acesso protegido por senha (st.secrets['painel']['senha']).
"""
import streamlit as st
import firebase_helper as fb

st.set_page_config(page_title="Nosferatu — Painel", page_icon="🩸", layout="wide")

# ===== Autenticação do painel =====
def checar_login():
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if not st.session_state.autenticado:
        st.title("🩸 Nosferatu — Painel de Controle")
        senha = st.text_input("Senha do painel", type="password")
        if st.button("Entrar"):
            try:
                if senha == st.secrets["painel"]["senha"]:
                    st.session_state.autenticado = True
                    st.rerun()
                else:
                    st.error("Senha incorreta")
            except Exception:
                st.error("Painel sem senha configurada. Defina st.secrets['painel']['senha'].")
        st.stop()

checar_login()

st.title("🩸 Nosferatu — Controle Remoto")
st.caption("Painel admin · dados seguros · service account só no servidor")

aba = st.tabs(["📊 Usuários", "🎯 Metas", "⚔️ Desafios", "🜏 Íncubo", "🔒 Limites/Bloqueios", "📢 Alertas"])

# ===== Helper UI =====
def listar_usuarios():
    try:
        docs = fb.fs_get("usuarios")
        us = []
        for d in docs.get("documents", []):
            us.append((d["name"].split("/")[-1], fb.fs_doc_to_dict(d)))
        return us
    except Exception as e:
        st.error(f"Erro ao listar: {e}")
        return []

@st.cache_data(ttl=10)
def _usuarios_cache():
    try:
        docs = fb.fs_get("usuarios")
        us = []
        for d in docs.get("documents", []):
            us.append((d["name"].split("/")[-1], fb.fs_doc_to_dict(d)))
        return us
    except Exception:
        return []

def selecionar_usuario(label="Usuário", key="sel_user"):
    us = _usuarios_cache()
    if not us:
        uid = st.text_input("UID do usuário (novo)", placeholder="ex: teste1", key=key + "_uid")
        return uid.strip() if uid else None
    nomes = [u[0] for u in us]
    idx = st.selectbox(label, nomes, index=0, key=key + "_sel")
    return idx

# ===== Aba Usuários =====
with aba[0]:
    st.subheader("📊 Usuários")
    st.caption("Crie contas com código + senha. O app valida pelo hash (senha nunca fica em claro).")
    us = _usuarios_cache()
    if us:
        for uid, d in us:
            st.markdown(f"**{uid}** — {d.get('nome', uid)} · nível {d.get('nivel', '?')} · "
                        f"lidos {d.get('livrosLidos', 0)}/{d.get('lidos_max', 10)} · "
                        f"páginas {d.get('paginasLidas', 0)} · ativo {d.get('ativo', True)}")
            if d.get("fcm_token"):
                st.caption(f"  ✅ FCM registrado ({d['fcm_token'][:20]}…)")
            else:
                st.caption("  ⚠️ Sem FCM (app ainda não abriu com Firebase)")
            st.divider()
    else:
        st.info("Nenhum usuário ainda. Crie abaixo — depois o app faz login com o código.")

    st.subheader("➕ Criar usuário")
    with st.form("criar_usuario_form"):
        c_nome = st.text_input("Nome (exibição)", placeholder="Maria")
        c_codigo = st.text_input("Código (login)", placeholder="lovalylady")
        c_senha = st.text_input("Senha", type="password")
        c_lidos = st.number_input("Limite de livros em LIDOS", min_value=1, max_value=500, value=10)
        enviar = st.form_submit_button("Criar usuário")
        if enviar:
            if not c_codigo or not c_senha:
                st.error("Código e senha obrigatórios")
            else:
                try:
                    fb.criar_usuario(c_codigo.strip(), c_nome.strip() or c_codigo.strip(), c_senha, int(c_lidos))
                    _usuarios_cache.clear()
                    st.success(f"Usuário '{c_codigo}' criado — já pode logar no app")
                except Exception as e:
                    st.error(f"Falha: {e}")

# ===== Aba Metas =====
with aba[1]:
    st.subheader("🎯 Metas")
    uid = selecionar_usuario("Usuário (meta)", key="meta")
    titulo = st.text_input("Título da meta", placeholder="Meta da semana")
    corpo = st.text_area("Descrição da meta", placeholder="Leia 50 páginas até sexta!", key="meta_corpo")
    if st.button("🚀 Disparar meta"):
        if not uid: st.error("Informe usuário")
        elif not titulo: st.error("Título obrigatório")
        else:
            try:
                fb.disparar_meta(uid, titulo, corpo or titulo)
                st.success(f"Meta enviada p/ {uid} — popup no topo do celular")
            except Exception as e:
                st.error(f"Falha: {e}")

# ===== Aba Desafios =====
with aba[2]:
    st.subheader("⚔️ Desafios")
    uid = selecionar_usuario("Usuário (desafio)", key="desafio")
    d_titulo = st.text_input("Título do desafio", placeholder="Desafio do íncubo")
    d_corpo = st.text_area("Descrição do desafio", placeholder="Complete 3 livros de true crime!", key="desafio_corpo")
    if st.button("⚔️ Disparar desafio"):
        if not uid: st.error("Informe usuário")
        elif not d_titulo: st.error("Título obrigatório")
        else:
            try:
                fb.disparar_desafio(uid, d_titulo, d_corpo or d_titulo)
                st.success(f"Desafio enviado p/ {uid}")
            except Exception as e:
                st.error(f"Falha: {e}")

# ===== Aba Íncubo =====
with aba[3]:
    st.subheader("🜏 Íncubo — invocação remota")
    uid = selecionar_usuario("Usuário (íncubo)", key="incubo")
    modo = st.radio("Modo de invocação", ["Agora (abre o app direto no íncubo)", "Próxima abertura (usuária vê no próximo open)"])
    if st.button("🜏 INVOCAR"):
        if not uid: st.error("Informe usuário")
        else:
            try:
                u = fb.usuario(uid)
                tok = u.get("fcm_token", "")
                if modo.startswith("Agora"):
                    if not tok: st.error("Sem FCM registrado")
                    else:
                        fb.enviar_push(tok, "🜏 O íncubo te chama…", "Toque para selar o pacto.", tipo="incubo", incubo="agora")
                        st.success("Íncubo invocado AGORA — popup desceu no celular")
                else:
                    fb.registrar_incubo_proxima_abertura(uid)
                    st.success("Íncubo marcado p/ PRÓXIMA ABERTURA — pacto selado quando abrir")
            except Exception as e:
                st.error(f"Falha: {e}")

# ===== Aba Limites/Bloqueios =====
with aba[4]:
    st.subheader("🔒 Limites e bloqueios por usuário")
    uid = selecionar_usuario("Usuário (limites)", key="limites")
    if uid:
        u = fb.usuario(uid)
        st.markdown(f"Editando: **{uid}**")
        lidos_max = st.number_input("Máx. livros em LIDOS", min_value=1, max_value=500, value=int(u.get("lidos_max", 10)))
        grimorio = st.selectbox("Grimório", ["liberado", "bloqueado"], index=0 if u.get("grimorio") != "bloqueado" else 1)
        paginas = st.selectbox("Páginas do grimório", ["todas", "nenhuma", "somente_nivel"], index=0 if u.get("paginas_liberadas") != "nenhuma" else 1)
        nivel_extra = st.number_input("Nível extra (bonificação)", min_value=0, max_value=100, value=int(u.get("nivel_extra", 0)))
        ativo = st.checkbox("Usuário ativo (app funciona)", value=bool(u.get("ativo", True)))
        if st.button("💾 Salvar limites"):
            fb.salvar_usuario(uid, {
                **u,
                "lidos_max": int(lidos_max),
                "grimorio": grimorio,
                "paginas_liberadas": paginas,
                "nivel_extra": int(nivel_extra),
                "ativo": bool(ativo),
            })
            _usuarios_cache.clear()
            st.success("Limites salvos — app aplica na próxima sincronização")

# ===== Aba Alertas =====
with aba[5]:
    st.subheader("📢 Alertas gerais")
    uid = selecionar_usuario("Usuário (alerta)", key="alerta")
    a_titulo = st.text_input("Título do alerta", placeholder="Lembrete")
    a_corpo = st.text_area("Mensagem", placeholder="Não esqueça sua meta de páginas de hoje!")
    if st.button("🔔 Enviar alerta"):
        if not uid: st.error("Informe usuário")
        elif not a_titulo: st.error("Título obrigatório")
        else:
            try:
                u = fb.usuario(uid)
                tok = u.get("fcm_token", "")
                if not tok: st.error("Sem FCM registrado")
                else:
                    fb.enviar_push(tok, a_titulo, a_corpo or a_titulo, tipo="aviso")
                    st.success("Alerta enviado")
            except Exception as e:
                st.error(f"Falha: {e}")

st.divider()
st.caption("🔒 Service account protegida — nunca versionar serviceAccountKey.json no GitHub.")
