import { html, useState, api, iniciar, Letreiro } from './lib.js';

const { obrigatoria, usuario } = window.DADOS;

function TrocarSenha() {
  const [atual, setAtual] = useState('');
  const [nova, setNova] = useState('');
  const [repetida, setRepetida] = useState('');
  const [erro, setErro] = useState('');
  const [enviando, setEnviando] = useState(false);

  const enviar = async (evento) => {
    evento.preventDefault();
    if (nova !== repetida) return setErro('As duas senhas novas não são iguais.');
    setEnviando(true);
    setErro('');
    try {
      const dados = await api('/api/minha-senha', { metodo: 'POST', corpo: { atual, nova } });
      location.href = dados.inicio;
    } catch (e) {
      setErro(e.message);
      setEnviando(false);
    }
  };
  const sair = async () => { await api('/api/logout', { metodo: 'POST' }); location.href = '/entrar'; };

  return html`<main class="porta azulejo">
    <form class="porta-placa" onSubmit=${enviar}>
      <div class="bandeira" aria-hidden="true"></div>
      <${Letreiro} classe="letreiro-grande" />
      <h1 class="porta-titulo">${obrigatoria ? 'Crie a sua senha' : 'Trocar minha senha'}</h1>
      ${obrigatoria && html`<p class="porta-texto">${usuario.nome}, a senha que você recebeu é provisória.
        Escolha uma que só você saiba para continuar.</p>`}
      <label class="rotulo" for="atual">${obrigatoria ? 'Senha provisória' : 'Senha atual'}</label>
      <input id="atual" class="campo" type="password" value=${atual} onInput=${(e) => setAtual(e.target.value)}
        autocomplete="current-password" required autofocus />
      <label class="rotulo" for="nova">Senha nova (8 caracteres ou mais)</label>
      <input id="nova" class="campo" type="password" value=${nova} onInput=${(e) => setNova(e.target.value)}
        autocomplete="new-password" minlength="8" required />
      <label class="rotulo" for="repetida">Repita a senha nova</label>
      <input id="repetida" class="campo" type="password" value=${repetida} onInput=${(e) => setRepetida(e.target.value)}
        autocomplete="new-password" minlength="8" required />
      ${erro && html`<p class="aviso" role="alert">${erro}</p>`}
      <button class="botao botao-primario botao-largo" disabled=${enviando}>${enviando ? 'Salvando…' : 'Salvar senha nova'}</button>
      <p class="porta-equipe">${obrigatoria
        ? html`<button type="button" class="link" onClick=${sair}>Sair</button>`
        : html`<a href="/entrar">Voltar</a>`}</p>
    </form>
  </main>`;
}

iniciar(TrocarSenha);
