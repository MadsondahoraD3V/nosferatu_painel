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

aba = st.tabs(["📊 Usuários", "🎯 Metas", "⚔️ Desafios", "🎁 Prêmios", "🜏 Íncubo", "🔒 Limites/Bloqueios", "📢 Alertas", "📜 Logs"])

# ===== Logs (histórico de ações do painel, em aba própria) =====
if "logs" not in st.session_state:
    st.session_state.logs = []

def _log(msg, tipo="info"):
    """Registra ação no histórico (aba Logs) — não polui a visualização."""
    import datetime as _dt
    st.session_state.logs.append(
        f"[{_dt.datetime.now().strftime('%d/%m %H:%M:%S')}] {tipo.upper()}: {msg}"
    )
    if len(st.session_state.logs) > 500:
        st.session_state.logs = st.session_state.logs[-500:]

# ===== Helper UI =====
def listar_usuarios():
    return _usuarios_cache()

def _mover_livro_painel(uid, livro, nova_coluna):
    """Muda a coluna de um livro do usuário no Firestore (livros_json + livros)."""
    try:
        import json as _json
        u = fb.usuario(uid)
        livros = u.get("livros") or []
        if isinstance(livros, str):
            livros = _json.loads(livros) if livros.strip() else []
        livros = list(livros)
        mudou = False
        for lb in livros:
            if isinstance(lb, dict) and lb.get("id") == livro.get("id"):
                lb["coluna"] = nova_coluna
                mudou = True
                break
        if mudou:
            # também atualiza livros_json (backup que o app restaura)
            j = []
            try:
                j = _json.loads(u.get("livros_json") or "[]")
            except Exception:
                j = []
            if isinstance(j, list):
                for lb in j:
                    if isinstance(lb, dict) and lb.get("id") == livro.get("id"):
                        lb["coluna"] = nova_coluna
                        break
            dados = {**u, "livros": livros}
            if j:
                dados["livros_json"] = _json.dumps(j, ensure_ascii=False)
            fb.salvar_usuario(uid, dados)
            _usuarios_cache.clear()
            _log(f"Livro '{livro.get('titulo','?')}' movido p/ {nova_coluna} (usuário {uid})", "livro")
            st.success(f"📖 '{livro.get('titulo','?')}' movido para {nova_coluna}")
        else:
            st.warning("Livro não encontrado no doc do usuário (sync ainda não subiu?)")
    except Exception as e:
        st.error(f"Falha ao mover: {e}")

def _editar_metadados_livro(uid, livro):
    """Form para editar metadados de um livro do usuário (categoria, título, autor, páginas)."""
    with st.form(key=f"meta_livro_{uid}_{livro.get('id','')}"):
        novo_titulo = st.text_input("Título", value=livro.get("titulo", ""), key=f"t_{uid}_{livro.get('id','')}")
        novo_autor = st.text_input("Autor", value=livro.get("autor", ""), key=f"a_{uid}_{livro.get('id','')}")
        nova_cat = st.text_input("Categoria", value=livro.get("categoria", ""), key=f"c_{uid}_{livro.get('id','')}")
        novas_pag = st.number_input("Páginas totais", min_value=1, max_value=100000,
                                    value=int(livro.get("paginasTotais", 1) or 1), key=f"p_{uid}_{livro.get('id','')}")
        sub = st.form_submit_button("💾 Salvar metadados")
        if sub:
            try:
                import json as _json
                u = fb.usuario(uid)
                livros = u.get("livros") or []
                if isinstance(livros, str):
                    livros = _json.loads(livros) if livros.strip() else []
                livros = list(livros)
                for lb in livros:
                    if isinstance(lb, dict) and lb.get("id") == livro.get("id"):
                        lb["titulo"] = novo_titulo.strip()
                        lb["autor"] = novo_autor.strip()
                        lb["categoria"] = nova_cat.strip()
                        lb["paginasTotais"] = int(novas_pag)
                        break
                j = []
                try:
                    j = _json.loads(u.get("livros_json") or "[]")
                except Exception:
                    j = []
                if isinstance(j, list):
                    for lb in j:
                        if isinstance(lb, dict) and lb.get("id") == livro.get("id"):
                            lb["titulo"] = novo_titulo.strip()
                            lb["autor"] = novo_autor.strip()
                            lb["categoria"] = nova_cat.strip()
                            lb["paginasTotais"] = int(novas_pag)
                            break
                dados = {**u, "livros": livros}
                if j:
                    dados["livros_json"] = _json.dumps(j, ensure_ascii=False)
                fb.salvar_usuario(uid, dados)
                _usuarios_cache.clear()
                _log(f"Metadados do livro '{livro.get('titulo','?')}' editados ({uid})", "livro")
                st.success("📖 Metadados salvos")
            except Exception as ex:
                st.error(f"Falha: {ex}")

@st.cache_data(ttl=10)
def _usuarios_cache():
    try:
        docs = fb.fs_get("usuarios")
        us = []
        for d in docs.get("documents", []):
            us.append((d["name"].split("/")[-1], fb.fs_doc_to_dict(d)))
        return us
    except Exception as e:
        st.session_state["erro_cache_usuarios"] = str(e)
        return []

def selecionar_usuario(label="Usuário", key="sel_user"):
    us = _usuarios_cache()
    if not us:
        err = st.session_state.pop("erro_cache_usuarios", "")
        if err:
            st.warning(f"⚠️ Não consegui listar usuários: {err[:200]}")
            st.caption("Se o erro for de private_key, atualize os Secrets do Streamlit e clique em 'Rerun' (menu ⋮ → Rerun).")
        uid = st.text_input("UID do usuário (digitar)", placeholder="ex: lovely_lady", key=key + "_uid")
        return uid.strip() if uid else None
    nomes = [u[0] for u in us]
    idx = st.selectbox(f"{label} ({len(nomes)} cadastrados)", nomes, index=0, key=key + "_sel")
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
                        f"páginas {d.get('paginasLidas', 0)} · grimório {d.get('paginas_grimorio', 0)} · "
                        f"ativo {d.get('ativo', True)}")
            if d.get("fcm_token"):
                st.caption(f"  ✅ FCM registrado ({d['fcm_token'][:20]}…)")
            else:
                st.caption("  ⚠️ Sem FCM (app ainda não abriu com Firebase)")
            # histórico de prêmios
            hist_u = d.get("premios_historico") or []
            if isinstance(hist_u, str):
                try:
                    import json as _json
                    hist_u = _json.loads(hist_u) if hist_u.strip() else []
                except Exception:
                    hist_u = []
            if hist_u:
                with st.expander(f"🏆 Prêmios de {uid} ({len(hist_u)})"):
                    for ph in list(hist_u)[-20:]:
                        if isinstance(ph, dict):
                            st.markdown(f"- {ph.get('premio','?')} · {ph.get('origem','')}")
            # Biblioteca do usuário (do backup livros_json ou array livros)
            livros_u = d.get("livros") or []
            if isinstance(livros_u, str):
                # doc antigo: livros salvo como string JSON — converte
                try:
                    import json as _json
                    livros_u = _json.loads(livros_u) if livros_u.strip() else []
                except Exception:
                    livros_u = []
            if livros_u:
                with st.expander(f"📚 Biblioteca de {uid} ({len(livros_u)} livros)"):
                    for lb in livros_u[:60]:
                        col = lb.get("coluna", "ler")
                        icone = {"ler": "📕", "lendo": "📖", "lidos": "✅"}.get(col, "📕")
                        c1, c2 = st.columns([4, 1])
                        with c1:
                            st.markdown(
                                f"{icone} **{lb.get('titulo','?')}** — {lb.get('autor','')} · "
                                f"{lb.get('paginasLidas',0)}/{lb.get('paginasTotais',0)}p · "
                                f"{'lido' if col=='lidos' else 'lendo' if col=='lendo' else 'para ler'}"
                            )
                        with c2:
                            nova_col = st.selectbox(
                                "coluna", ["ler", "lendo", "lidos"],
                                index={"ler": 0, "lendo": 1, "lidos": 2}.get(col, 0),
                                key=f"col_{uid}_{lb.get('id','')}", label_visibility="collapsed")
                            if nova_col != col:
                                _mover_livro_painel(uid, lb, nova_col)
                        with st.expander(f"✏️ Editar metadados de '{lb.get('titulo','?')}'"):
                            _editar_metadados_livro(uid, lb)
            st.divider()
    else:
        st.info("Nenhum usuário ainda. Crie abaixo — depois o app faz login com o código.")

    st.subheader("🔑 Editar usuário / senha")
    with st.form("editar_usuario_form"):
        e_uid = st.selectbox("Usuário", [u[0] for u in us] if us else [], key="editar_sel")
        e_nome = st.text_input("Nome (deixe vazio p/ manter)", placeholder="Novo nome")
        e_senha = st.text_input("Nova senha (deixe vazio p/ manter)", type="password")
        e_lidos = st.number_input("Limite LIDOS", min_value=1, max_value=500, value=10)
        e_paginas = st.number_input("Páginas acumuladas", min_value=0, max_value=100000, value=0,
                                    help="Total de páginas lidas da biblioteca (contador geral)")
        e_grimorio = st.number_input("Páginas do Grimório", min_value=0, max_value=10000, value=0,
                                     help="Páginas do grimório ganhas em metas/desafios (10 = 1 grimório completo)")
        e_nivel = st.number_input("Nível", min_value=1, max_value=999, value=1)
        e_pontos = st.number_input("Pontos", min_value=0, max_value=100000, value=0)
        e_editar = st.form_submit_button("💾 Salvar alterações")
        if e_editar:
            if not e_uid:
                st.error("Selecione usuário")
            else:
                try:
                    u = fb.usuario(e_uid)
                    if not u.get("uid"):
                        u = {"uid": e_uid}
                    dados = {**u, "lidos_max": int(e_lidos)}
                    if e_nome.strip():
                        dados["nome"] = e_nome.strip()
                    if e_senha:
                        h, salt = fb._hash_senha(e_senha)
                        dados["senha_hash"] = h
                        dados["senha_salt"] = salt
                    # campos de progresso (só sobrescreve se o usuário digitou algo)
                    if e_paginas > 0 or u.get("paginasLidas"):
                        dados["paginasLidas"] = int(e_paginas)
                    if e_grimorio > 0 or u.get("paginas_grimorio"):
                        dados["paginas_grimorio"] = int(e_grimorio)
                    if e_nivel > 0:
                        dados["nivel"] = int(e_nivel)
                    if e_pontos > 0 or u.get("pontos"):
                        dados["pontos"] = int(e_pontos)
                    fb.salvar_usuario(e_uid, dados)
                    _usuarios_cache.clear()
                    _log(f"Usuário '{e_uid}' atualizado (nome={e_nome.strip() or 'mantido'}, lidos_max={int(e_lidos)}, "
                         f"páginas={int(e_paginas)}, grimório={int(e_grimorio)}, nível={int(e_nivel)}, pontos={int(e_pontos)})", "usuario")
                    st.success(f"Usuário '{e_uid}' atualizado")
                except Exception as ex:
                    _log(f"Falha editar {e_uid}: {ex}", "erro")
                    st.error(f"Falha: {ex}")

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
                    _log(f"Usuário criado: {c_codigo.strip()} ({c_nome.strip() or c_codigo.strip()}, lidos_max={int(c_lidos)})", "usuario")
                    st.success(f"Usuário '{c_codigo}' criado — já pode logar no app")
                except Exception as e:
                    _log(f"Falha criar {c_codigo}: {e}", "erro")
                    st.error(f"Falha: {e}")

# ===== Aba Metas =====
with aba[1]:
    st.subheader("🎯 Metas com prazo")
    st.caption("Meta = N páginas em até X dias. Venceu cumprindo → ganha prêmio. Prazo expirou sem cumprir → fresh meat +1.")
    uid = selecionar_usuario("Usuário (meta)", key="meta")
    m_titulo = st.text_input("Título da meta", placeholder="Meta da semana", key="meta_titulo")
    m_corpo = st.text_area("Descrição", placeholder="Leia 200 páginas em 7 dias!", key="meta_corpo")
    m_paginas = st.number_input("Total de páginas", min_value=1, max_value=5000, value=200, key="meta_paginas")
    m_dias = st.number_input("Prazo (dias)", min_value=1, max_value=90, value=7, key="meta_dias")
    try:
        premios_meta = fb.listar_premios()
        nomes_meta = [pr.get("nome", "?") for pr in premios_meta]
    except Exception:
        nomes_meta = ["📄 Página do Grimório"]
    m_premio = st.selectbox("Prêmio", nomes_meta, key="meta_premio")
    st.caption("🩸 Penalidades em caso de FALHA (prazo expira sem cumprir):")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        m_perde_paginas = st.checkbox("Perde páginas (progresso zerado)", value=True, key="meta_perde_paginas")
    with col_p2:
        m_perde_carne = st.checkbox("Perde pedaço de carne (Punição do Íncubo)", value=True, key="meta_perde_carne")
    if st.button("📌 Cadastrar meta"):
        if not uid: st.error("Informe usuário")
        elif not m_titulo: st.error("Título obrigatório")
        else:
            try:
                import time as _t
                # id FIXO = uid: app lê doc único (regras Firestore: uid == resource.data.uid;
                # lista é bloqueada p/ token anônimo). 1 meta ativa por usuário.
                fb.fs_set("metas", uid, {
                    "uid": uid, "titulo": m_titulo, "descricao": m_corpo or m_titulo,
                    "paginas_total": int(m_paginas), "validade_ts": int(_t.time()) + int(m_dias) * 86400,
                    "premio": m_premio, "criada_ts": int(_t.time()), "aderida": True,
                    "resultado": "", "premio_entregue": False,
                    "perde_paginas": bool(m_perde_paginas), "perde_carne": bool(m_perde_carne),
                })
                _log(f"Meta cadastrada p/ {uid}: {m_titulo} ({int(m_paginas)}p em {int(m_dias)}d, prêmio: {m_premio}, perde páginas: {bool(m_perde_paginas)}, perde carne: {bool(m_perde_carne)})", "meta")
                st.success(f"Meta cadastrada p/ {uid}")
            except Exception as e:
                _log(f"Falha meta {uid}: {e}", "erro")
                st.error(f"Falha: {e}")

    st.subheader("📋 Metas ativas")
    try:
        metas = fb.fs_get("metas")
        for d in metas.get("documents", []):
            m = fb.fs_doc_to_dict(d)
            if m.get("uid") != (uid or ""): continue
            res = m.get("resultado", "")
            badge = {"venceu": "🏆", "perdeu": "💀", "": "⏳"}.get(res, "⏳")
            st.markdown(f"**{m.get('titulo','?')}** · {m.get('paginas_total','?')} páginas · "
                        f"prêmio: {m.get('premio','📄 Página do Grimório')} · {badge} {res or 'em andamento'} · "
                        f"válida até {_t.strftime('%d/%m', _t.localtime(m.get('validade_ts', 0)))}")
    except Exception as e:
        st.error(f"Erro metas: {e}")

# ===== Aba Desafios =====
with aba[2]:
    st.subheader("⚔️ Desafios")
    uid = selecionar_usuario("Usuário (desafio)", key="desafio")
    d_titulo = st.text_input("Título do desafio", placeholder="Desafio do íncubo")
    d_corpo = st.text_area("Descrição do desafio", placeholder="Complete 3 livros de true crime!", key="desafio_corpo")
    st.caption("🩸 Penalidades em caso de FALHA do desafio:")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        d_perde_paginas = st.checkbox("Perde páginas (progresso zerado)", value=True, key="desafio_perde_paginas")
    with col_d2:
        d_perde_carne = st.checkbox("Perde pedaço de carne (Punição do Íncubo)", value=True, key="desafio_perde_carne")
    if st.button("⚔️ Disparar desafio"):
        if not uid: st.error("Informe usuário")
        elif not d_titulo: st.error("Título obrigatório")
        else:
            try:
                fb.disparar_desafio(uid, d_titulo, d_corpo or d_titulo, perde_paginas=bool(d_perde_paginas), perde_carne=bool(d_perde_carne))
                _log(f"Desafio enviado p/ {uid}: {d_titulo} (perde páginas: {bool(d_perde_paginas)}, perde carne: {bool(d_perde_carne)})", "desafio")
                st.success(f"Desafio enviado p/ {uid}")
            except Exception as e:
                _log(f"Falha desafio {uid}: {e}", "erro")
                st.error(f"Falha: {e}")

# ===== Aba Prêmios =====
with aba[3]:
    st.subheader("🎁 Prêmios — catálogo dinâmico")
    st.caption("Cadastre novos prêmios ou credite diretamente a um usuário. Metas/desafios usam este catálogo.")

    try:
        premios = fb.listar_premios()
        st.markdown("**Catálogo atual:**")
        for pr in premios:
            tipo = "📄 página grimório" if pr.get("tipo") == "pagina_grimorio" else "🎁 item"
            st.markdown(f"- {pr.get('nome','?')} · {tipo}" + (f" · R${pr.get('valor',0)}" if pr.get('valor') else ""))
    except Exception as e:
        st.error(f"Erro prêmios: {e}")

    st.divider()
    st.subheader("➕ Cadastrar novo prêmio")
    with st.form("premio_form"):
        p_nome = st.text_input("Nome do prêmio", placeholder="ex: 🎧 Fone Bluetooth")
        p_tipo = st.selectbox("Tipo", ["item", "pagina_grimorio"], format_func=lambda t: "🎁 Item" if t == "item" else "📄 Página do Grimório")
        p_valor = st.number_input("Valor (R$, opcional)", min_value=0, max_value=10000, value=0)
        p_enviar = st.form_submit_button("💾 Cadastrar prêmio")
        if p_enviar:
            if not p_nome.strip():
                st.error("Nome obrigatório")
            else:
                try:
                    fb.cadastrar_premio(p_nome.strip(), p_tipo, int(p_valor))
                    _log(f"Prêmio cadastrado: {p_nome.strip()} ({p_tipo})", "premio")
                    st.success(f"Prêmio '{p_nome.strip()}' cadastrado")
                except Exception as e:
                    _log(f"Falha prêmio {p_nome}: {e}", "erro")
                    st.error(f"Falha: {e}")

    st.divider()
    st.subheader("🎯 Creditar prêmio a um usuário")
    p_uid = selecionar_usuario("Usuário (creditar)", key="creditar")
    if p_uid:
            nomes = [pr.get("nome", "?") for pr in premios]
            p_sel = st.selectbox("Prêmio", nomes, key="creditar_premio_sel")
            if st.button("🎁 Creditar"):
                try:
                    fb.creditar_premio(p_uid, p_sel)
                    _usuarios_cache.clear()
                    _log(f"Prêmio '{p_sel}' creditado p/ {p_uid}", "premio")
                    st.success(f"Prêmio '{p_sel}' creditado p/ {p_uid}")
                except Exception as e:
                    _log(f"Falha creditar {p_uid}: {e}", "erro")
                    st.error(f"Falha: {e}")

# ===== Aba Íncubo =====
with aba[4]:
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
                    if not tok:
                        _log(f"Invocação AGORA sem FCM p/ {uid}", "erro")
                        st.error("Sem FCM registrado")
                    else:
                        fb.enviar_push(tok, "🜏 O íncubo te chama…", "Toque para selar o pacto.", tipo="incubo", incubo="agora")
                        _log(f"Íncubo invocado AGORA p/ {uid}", "incubo")
                        st.success("Íncubo invocado AGORA — popup desceu no celular")
                else:
                    fb.registrar_incubo_proxima_abertura(uid)
                    _log(f"Íncubo marcado p/ PRÓXIMA ABERTURA p/ {uid}", "incubo")
                    st.success("Íncubo marcado p/ PRÓXIMA ABERTURA — pacto selado quando abrir")
            except Exception as e:
                _log(f"Falha íncubo {uid}: {e}", "erro")
                st.error(f"Falha: {e}")

# ===== Aba Limites/Bloqueios =====
with aba[5]:
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
            _log(f"Limites salvos p/ {uid}: lidos_max={int(lidos_max)}, grimorio={grimorio}, ativo={bool(ativo)}", "limites")
            st.success("Limites salvos — app aplica na próxima sincronização")

# ===== Aba Alertas =====
with aba[6]:
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
                if not tok:
                    _log(f"Alerta sem FCM p/ {uid} → grava em alertas (pull)", "alerta")
                    st.info("Sem FCM registrado — alerta entra na fila de pull (app puxa em ~15s)")
                    import time as _t
                    # id FIXO = uid: app lê doc único (lista é bloqueada p/ token anônimo)
                    fb.fs_set("alertas", uid, {
                        "uid": uid, "titulo": a_titulo, "corpo": a_corpo or a_titulo,
                        "horario_ts": int(_t.time() * 1000), "enviado": False,
                    })
                    st.success("Alerta na fila (sem FCM, via pull)")
                else:
                    fb.enviar_push(tok, a_titulo, a_corpo or a_titulo, tipo="aviso")
                    _log(f"Alerta enviado p/ {uid}: {a_titulo}", "alerta")
                    st.success("Alerta enviado")
            except Exception as e:
                _log(f"Falha alerta {uid}: {e}", "erro")
                st.error(f"Falha: {e}")

    st.divider()
    st.subheader("🕐 Agendar alerta")
    st.caption("Agenda no horário escolhido. O app mostra quando estiver na hora (não precisa de push).")
    ag_uid = st.text_input("Código do usuário (agendar)", key="alg_uid", placeholder="madson")
    ag_titulo = st.text_input("Título", key="alg_tit", placeholder="Hora da leitura")
    ag_corpo = st.text_area("Mensagem", key="alg_corpo", placeholder="Está na hora de ler 🩸")
    ag_data = st.date_input("Data (agendar)", key="alg_data")
    ag_hora = st.time_input("Hora (agendar)", key="alg_hora")
    if st.button("📅 Agendar alerta"):
        import datetime as _dt
        if not ag_uid or not ag_titulo:
            st.error("Código e título obrigatórios")
        else:
            try:
                nao_ts = int(_dt.datetime.combine(ag_data, ag_hora).replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
                # id FIXO = uid: app lê doc único (lista bloqueada p/ token anônimo)
                fb.fs_set("alertas", ag_uid, {
                    "uid": ag_uid, "titulo": ag_titulo, "corpo": ag_corpo or ag_titulo,
                    "horario_ts": nao_ts, "enviado": False,
                })
                _log(f"Alerta agendado p/ {ag_uid} em {ag_data} {ag_hora}", "alerta")
                st.success(f"Alerta agendado p/ {ag_uid} em {ag_data} {ag_hora}")
            except Exception as e:
                st.error(f"Falha ao agendar: {e}")

    st.divider()
    st.subheader("🔁 Alerta recorrente (todo dia)")
    st.caption("Repete diariamente no horário definido — título e corpo fixos. O app checa na sincronização.")
    rc_uid = st.text_input("Código do usuário (recorrente)", key="rc_uid", placeholder="madson")
    rc_titulo = st.text_input("Título (recorrente)", key="rc_tit", placeholder="Hora da leitura")
    rc_corpo = st.text_area("Mensagem (recorrente)", key="rc_corpo", placeholder="Está na hora de ler 🩸")
    rc_hora = st.time_input("Horário diário (recorrente)", key="rc_hora", value=_dt.time(20, 0))
    if st.button("🔁 Ativar recorrente"):
        if not rc_uid or not rc_titulo:
            st.error("Código e título obrigatórios")
        else:
            try:
                import datetime as _dt
                # guarda o horário diário + flag recorrente; id fixo = uid (doc único)
                fb.fs_set("alertas", rc_uid, {
                    "uid": rc_uid, "titulo": rc_titulo, "corpo": rc_corpo or rc_titulo,
                    "recorrente": True, "hora": f"{rc_hora.hour:02d}:{rc_hora.minute:02d}",
                    "horario_ts": 0, "enviado": False,
                })
                _log(f"Alerta RECORRENTE ativado p/ {rc_uid} às {rc_hora.hour:02d}:{rc_hora.minute:02d}", "alerta")
                st.success(f"Recorrente ativado p/ {rc_uid} — todo dia às {rc_hora.hour:02d}:{rc_hora.minute:02d}")
            except Exception as e:
                st.error(f"Falha ao ativar recorrente: {e}")

# ===== Aba Logs =====
with aba[7]:
    st.subheader("📜 Logs de ações")
    st.caption("Histórico do que foi feito no painel (últimas 500). Não polui as abas de uso.")
    if not st.session_state.logs:
        st.info("Nenhuma ação registrada ainda.")
    for l in st.session_state.logs[::-1]:
        st.code(l, language=None)
    if st.button("🧹 Limpar logs"):
        st.session_state.logs = []
        st.rerun()

st.divider()
st.caption("🔒 Service account protegida — nunca versionar serviceAccountKey.json no GitHub.")
