import {
  html, useState, api, avisar, iniciar, useDados, useCarrinho, useRelogio, reais, mesa2, hora, tempoDecorrido,
  Cardapio, FolhaCarrinho, ItensPedido, Selo, BarraEquipe, Icone,
} from './lib.js';

const USUARIO = window.DADOS.usuario;
const FILTROS = [['todas', 'Todas'], ['aguardando', 'Aguardando'], ['ocupada', 'Ocupadas'], ['livre', 'Livres']];
const TEXTO_CHAMADO = { garcom: 'Chamou o garçom', conta: 'Pediu a conta' };

function Salao({ mesas, aoAbrir }) {
  const [filtro, setFiltro] = useState('todas');
  useRelogio(30);
  const contagem = (status) => mesas.filter((m) => status === 'todas' || m.status === status).length;
  const visiveis = mesas.filter((m) => filtro === 'todas' || m.status === filtro);

  return html`<main class="salao">
    <div class="filtros" role="tablist" aria-label="Filtrar mesas">
      ${FILTROS.map(([valor, rotulo]) => html`<button key=${valor} role="tab" aria-selected=${filtro === valor}
        class="filtro ${filtro === valor ? 'ativa' : ''} ${valor === 'aguardando' && contagem(valor) > 0 ? 'alerta' : ''}"
        onClick=${() => setFiltro(valor)}>${rotulo} <span>${contagem(valor)}</span></button>`)}
    </div>
    ${visiveis.length === 0 && html`<p class="vazio">Nenhuma mesa neste filtro.</p>`}
    <ul class="mesas">
      ${visiveis.map((m) => html`<li key=${m.id}>
        <button class="mesa mesa-${m.status}" onClick=${() => aoAbrir(m.id)}>
          <span class="mesa-numero">${mesa2(m.numero)}</span>
          ${m.status === 'livre' && html`<span class="mesa-estado">Livre</span>`}
          ${m.status === 'aguardando' && html`<span class="mesa-estado"><${Icone} nome="sino" tamanho=${15} />
            ${TEXTO_CHAMADO[m.chamado]}</span>`}
          ${m.status === 'ocupada' && html`<span class="mesa-estado">Ocupada há ${tempoDecorrido(m.aberta_em)}</span>`}
          ${m.comanda_id && html`<span class="mesa-total">${reais(m.subtotal)}</span>`}
          ${m.pedidos_prontos > 0 && html`<span class="mesa-pronto">${m.pedidos_prontos} pronto${m.pedidos_prontos > 1 ? 's' : ''} para levar</span>`}
        </button>
      </li>`)}
    </ul>
  </main>`;
}

function Mesa({ mesaId, aoVoltar, aoLancar }) {
  const { dados: mesa, erro, recarregar } = useDados(`/api/mesas/${mesaId}`, ['pedidos', 'mesas']);
  const [ocupado, setOcupado] = useState(false);

  const agir = async (caminho, corpo, mensagem) => {
    setOcupado(true);
    try {
      await api(caminho, { metodo: 'POST', corpo });
      await recarregar();
      avisar(mensagem);
    } catch (e) { avisar(e.message, 'erro'); }
    setOcupado(false);
  };

  if (!mesa) return html`<main class="mesa-detalhe"><p class="carregando">${erro || 'Abrindo a mesa…'}</p></main>`;
  const pedidos = [...mesa.pedidos].reverse();

  return html`<main class="mesa-detalhe">
    <div class="mesa-cabecalho">
      <button class="botao-icone" onClick=${aoVoltar} aria-label="Voltar para as mesas"><${Icone} nome="voltar" /></button>
      <h1>Mesa ${mesa2(mesa.numero)}</h1>
      <span class="mesa-resumo">${mesa.comanda_id ? reais(mesa.subtotal) : 'Livre'}</span>
    </div>

    ${mesa.chamado && html`<div class="chamado-garcom">
      <p><${Icone} nome="sino" tamanho=${18} /> ${TEXTO_CHAMADO[mesa.chamado]} às ${hora(mesa.chamado_em)}</p>
      <button class="botao botao-escuro" disabled=${ocupado}
        onClick=${() => agir(`/api/mesas/${mesa.id}/atender`, undefined, 'Mesa atendida')}>Marcar como atendida</button>
    </div>`}

    <button class="botao botao-primario botao-largo" onClick=${aoLancar}>
      <${Icone} nome="mais" /> Lançar pedido
    </button>

    ${pedidos.length === 0 && html`<p class="vazio">Mesa livre. Lance o primeiro pedido para abrir a conta.</p>`}
    ${pedidos.map((p) => html`<article key=${p.id} class="pedido-garcom">
      <header>
        <h2>${hora(p.criado_em)} <small>${p.origem === 'cliente' ? 'pelo QR Code' : `por ${p.atendente || 'garçom'}`}</small></h2>
        <${Selo} status=${p.status} />
      </header>
      <${ItensPedido} itens=${p.itens} />
      <footer>
        <span>${reais(p.total)}</span>
        ${p.status === 'pronto' && html`<button class="botao botao-verde" disabled=${ocupado}
          onClick=${() => agir(`/api/pedidos/${p.id}/status`, { status: 'entregue' }, 'Pedido entregue na mesa')}>
          <${Icone} nome="check" tamanho=${18} /> Entreguei na mesa</button>`}
        ${p.status === 'pendente' && html`<button class="botao botao-fantasma" disabled=${ocupado}
          onClick=${() => { if (confirm('Cancelar este pedido?')) agir(`/api/pedidos/${p.id}/status`, { status: 'cancelado' }, 'Pedido cancelado'); }}>
          Cancelar pedido</button>`}
      </footer>
    </article>`)}
  </main>`;
}

function Lancar({ mesaId, numero, aoVoltar, aoConcluir }) {
  const cardapio = useDados('/api/cardapio', ['cardapio']);
  const carrinho = useCarrinho(`lagiovanna-garcom-mesa-${mesaId}`);
  const [aberto, setAberto] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const enviar = async () => {
    setEnviando(true);
    try {
      await api(`/api/mesas/${mesaId}/pedidos`, { metodo: 'POST', corpo: { itens: carrinho.paraEnvio() } });
      carrinho.limpar();
      avisar(`Pedido da mesa ${mesa2(numero)} enviado para a cozinha`);
      aoConcluir();
    } catch (e) {
      avisar(e.message, 'erro');
      if (e.status === 409) cardapio.recarregar();
      setEnviando(false);
    }
  };

  return html`<main class="lancar">
    <div class="mesa-cabecalho">
      <button class="botao-icone" onClick=${aoVoltar} aria-label="Voltar para a mesa"><${Icone} nome="voltar" /></button>
      <h1>Pedido da mesa ${mesa2(numero)}</h1>
    </div>
    ${!cardapio.dados && html`<p class="carregando">${cardapio.erro || 'Abrindo o cardápio…'}</p>`}
    ${cardapio.dados && html`<${Cardapio} cardapio=${cardapio.dados} carrinho=${carrinho} busca=${true} />`}
    <div class="barra-pedido">
      <button class="botao botao-primario barra-pedido-ver" disabled=${carrinho.quantidade === 0} onClick=${() => setAberto(true)}>
        ${carrinho.quantidade === 0
          ? 'Toque nos itens para lançar'
          : html`Conferir pedido (${carrinho.quantidade}) <span class="botao-valor">${reais(carrinho.total)}</span>`}
      </button>
    </div>
    ${aberto && html`<${FolhaCarrinho} carrinho=${carrinho} titulo="Pedido da mesa ${mesa2(numero)}"
      textoEnviar="Enviar para a cozinha" enviando=${enviando} aoEnviar=${enviar} aoFechar=${() => setAberto(false)} />`}
  </main>`;
}

function Garcom() {
  const mesas = useDados('/api/mesas', ['pedidos', 'mesas']);
  const [mesaId, setMesaId] = useState(null);
  const [lancando, setLancando] = useState(false);
  const mesa = mesas.dados?.find((m) => m.id === mesaId);

  return html`<div class="garcom">
    <${BarraEquipe} titulo="Salão" usuario=${USUARIO}>
      ${USUARIO.perfil === 'admin' && html`<a class="botao botao-fantasma" href="/admin">Gerência</a>`}
    <//>
    ${!mesas.dados && html`<p class="carregando">${mesas.erro || 'Carregando as mesas…'}</p>`}
    ${mesas.dados && !mesa && html`<${Salao} mesas=${mesas.dados} aoAbrir=${setMesaId} />`}
    ${mesa && !lancando && html`<${Mesa} mesaId=${mesa.id} aoVoltar=${() => { setMesaId(null); mesas.recarregar(); }} aoLancar=${() => setLancando(true)} />`}
    ${mesa && lancando && html`<${Lancar} mesaId=${mesa.id} numero=${mesa.numero}
      aoVoltar=${() => setLancando(false)} aoConcluir=${() => setLancando(false)} />`}
  </div>`;
}

iniciar(Garcom);
