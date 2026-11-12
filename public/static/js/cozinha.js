import {
  html, useState, useEffect, useRef, api, avisar, iniciar, useDados, useRelogio, mesa2, hora, minutosDesde,
  ItensPedido, BarraEquipe, Icone,
} from './lib.js';

const USUARIO = window.DADOS.usuario;
const COLUNAS = [
  { status: 'pendente', titulo: 'Pendentes', vazio: 'Nenhum pedido esperando.', avancar: ['preparo', 'Começar preparo'] },
  { status: 'preparo', titulo: 'Em preparo', vazio: 'Nada no forno agora.', avancar: ['pronto', 'Marcar como pronto'], voltar: ['pendente', 'Voltar para pendentes'] },
  { status: 'pronto', titulo: 'Prontos', vazio: 'Nenhum pedido aguardando o garçom.', voltar: ['preparo', 'Voltar para preparo'] },
];

function tocarSino() {
  try {
    const audio = new (window.AudioContext || window.webkitAudioContext)();
    [880, 1175].forEach((frequencia, i) => {
      const oscilador = audio.createOscillator();
      const ganho = audio.createGain();
      oscilador.frequency.value = frequencia;
      oscilador.connect(ganho);
      ganho.connect(audio.destination);
      const inicio = audio.currentTime + i * 0.18;
      ganho.gain.setValueAtTime(0.25, inicio);
      ganho.gain.exponentialRampToValueAtTime(0.001, inicio + 0.5);
      oscilador.start(inicio);
      oscilador.stop(inicio + 0.5);
    });
  } catch { /* navegador sem áudio */ }
}

function Comanda({ pedido, coluna, aoMover, ocupado }) {
  const espera = minutosDesde(pedido.criado_em);
  const urgencia = pedido.status === 'pronto' ? '' : espera >= 20 ? 'atrasado' : espera >= 10 ? 'atencao' : '';
  return html`<article class="comanda ${urgencia}">
    <header class="comanda-topo">
      <p class="comanda-mesa"><span>Mesa</span><strong>${mesa2(pedido.mesa)}</strong></p>
      <p class="comanda-tempo">
        <span><${Icone} nome="relogio" tamanho=${15} /> ${espera} min</span>
        <small>entrou às ${hora(pedido.criado_em)}</small>
      </p>
    </header>
    <${ItensPedido} itens=${pedido.itens.filter((i) => !i.cancelado)} />
    <footer class="comanda-acoes">
      ${coluna.avancar && html`<button class="botao botao-primario botao-largo" disabled=${ocupado}
        onClick=${() => aoMover(pedido, coluna.avancar[0])}>${coluna.avancar[1]}</button>`}
      ${coluna.voltar && html`<button class="botao botao-fantasma" disabled=${ocupado}
        onClick=${() => aoMover(pedido, coluna.voltar[0])}>${coluna.voltar[1]}</button>`}
    </footer>
  </article>`;
}

function Cozinha() {
  const { dados: pedidos, erro, recarregar } = useDados('/api/cozinha/pedidos', ['pedidos']);
  const [aba, setAba] = useState('pendente');
  const [som, setSom] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const conhecidos = useRef(null);
  useRelogio(20);

  useEffect(() => {
    if (!pedidos) return;
    const pendentes = pedidos.filter((p) => p.status === 'pendente').map((p) => p.id);
    if (conhecidos.current && som && pendentes.some((id) => !conhecidos.current.has(id))) tocarSino();
    conhecidos.current = new Set(pedidos.map((p) => p.id));
  }, [pedidos]);

  const mover = async (pedido, status) => {
    setOcupado(true);
    try {
      await api(`/api/pedidos/${pedido.id}/status`, { metodo: 'POST', corpo: { status } });
      await recarregar();
    } catch (e) { avisar(e.message, 'erro'); recarregar(); }
    setOcupado(false);
  };

  const daColuna = (status) => (pedidos || []).filter((p) => p.status === status);

  return html`<div class="cozinha">
    <${BarraEquipe} titulo="Cozinha" usuario=${USUARIO}>
      <button class="botao botao-fantasma ${som ? 'ligado' : ''}" aria-pressed=${som}
        onClick=${() => { if (!som) tocarSino(); setSom(!som); }}>
        <${Icone} nome="som" tamanho=${18} /> ${som ? 'Som ligado' : 'Ligar som'}
      </button>
      ${USUARIO.perfil === 'admin' && html`<a class="botao botao-fantasma" href="/admin">Gerência</a>`}
    <//>
    ${!pedidos && html`<p class="carregando">${erro || 'Carregando os pedidos…'}</p>`}
    ${pedidos && html`
      <div class="cozinha-abas" role="tablist">
        ${COLUNAS.map((c) => html`<button key=${c.status} role="tab" aria-selected=${aba === c.status}
          class=${aba === c.status ? 'ativa' : ''} onClick=${() => setAba(c.status)}>
          ${c.titulo} <span>${daColuna(c.status).length}</span></button>`)}
      </div>
      <main class="quadro">
        ${COLUNAS.map((c) => html`<section key=${c.status} class="coluna coluna-${c.status} ${aba === c.status ? 'visivel' : ''}">
          <h2>${c.titulo} <span>${daColuna(c.status).length}</span></h2>
          ${daColuna(c.status).length === 0 && html`<p class="coluna-vazia">${c.vazio}</p>`}
          ${daColuna(c.status).map((p) => html`<${Comanda} key=${p.id} pedido=${p} coluna=${c} aoMover=${mover} ocupado=${ocupado} />`)}
        </section>`)}
      </main>`}
  </div>`;
}

iniciar(Cozinha);
