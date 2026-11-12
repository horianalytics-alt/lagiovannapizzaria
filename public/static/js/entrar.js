import { html, useState, api, iniciar, Letreiro } from './lib.js';

function Entrar() {
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);

  const enviar = async (evento) => {
    evento.preventDefault();
    setEnviando(true);
    setErro('');
    try {
      const dados = await api('/api/login', { metodo: 'POST', corpo: { usuario, senha } });
      const proximo = new URLSearchParams(location.search).get('proximo') || '';
      const interno = /^\/[a-z0-9/_-]{0,80}$/.test(proximo);
      location.href = dados.trocar_senha ? '/trocar-senha' : interno ? proximo : dados.inicio;
    } catch (e) {
      setErro(e.message);
      setEnviando(false);
    }
  };

  return html`<main class="porta azulejo">
    <form class="porta-placa" onSubmit=${enviar}>
      <div class="bandeira" aria-hidden="true"></div>
      <${Letreiro} classe="letreiro-grande" />
      <h1 class="porta-titulo">Entrada da equipe</h1>
      <label class="rotulo" for="usuario">Usuário</label>
      <input id="usuario" class="campo" value=${usuario} onInput=${(e) => setUsuario(e.target.value)}
        autocomplete="username" autocapitalize="none" spellcheck=${false} required autofocus />
      <label class="rotulo" for="senha">Senha</label>
      <input id="senha" class="campo" type="password" value=${senha} onInput=${(e) => setSenha(e.target.value)}
        autocomplete="current-password" required />
      ${erro && html`<p class="aviso" role="alert">${erro}</p>`}
      <button class="botao botao-primario botao-largo" disabled=${enviando}>${enviando ? 'Entrando…' : 'Entrar'}</button>
      <p class="porta-equipe">É cliente? <a href="/">Abrir o cardápio da mesa</a></p>
      <p class="porta-equipe"><a href="/privacidade">Aviso de privacidade</a></p>
    </form>
  </main>`;
}

iniciar(Entrar);
