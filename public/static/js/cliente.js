import {
  html, useState, api, avisar, iniciar, useDados, useCarrinho, reais, mesa2, hora,
  Cardapio, FolhaCarrinho, Folha, ItensPedido, Letreiro, Icone,
} from './lib.js';

const MESA = window.DADOS.mesa;
const ETAPAS = ['pendente', 'preparo', 'pronto', 'entregue'];
const NOME_ETAPA = { pendente: 'Recebido', preparo: 'No forno', pronto: 'Pronto', entregue: 'Na mesa' };

function Andamento({ status }) {
  if (status === 'cancelado') return html`<p class="andamento-cancelado">Pedido cancelado</p>`;
  const atual = ETAPAS.indexOf(status);
  return html`<ol class="andamento" aria-label="Andamento: ${NOME_ETAPA[status]}">
    ${ETAPAS.map((etapa, i) => html`<li key=${etapa}
      class=${i < atual ? 'feita' : i === atual ? 'atual' : ''} aria-current=${i === atual ? 'step' : null}>
      <span class="andamento-ponto">${i < atual && html`<${Icone} nome="check" tamanho=${12} />`}</span>
      <span>${NOME_ETAPA[etapa]}</span>
    </li>`)}
  </ol>`;
}

function MeusPedidos({ mesa, aoFechar, recarregar }) {
  const [chamando, setChamando] = useState(false);
  const chamar = async (tipo) => {
    setChamando(true);
    try {
      await api(`/api/mesa/${MESA}/chamar`, { metodo: 'POST', corpo: { tipo } });
      await recarregar();
      avisar(tipo === 'conta' ? 'Conta pedida. Já levamos até você.' : 'Garçom chamado. Ele já vem.');
    } catch (e) { avisar(e.message, 'erro'); }
    setChamando(false);
  };
  const pedidos = [...mesa.pedidos].reverse();

  return html`<${Folha} titulo="Pedidos da mesa ${mesa2(MESA)}" aoFechar=${aoFechar}>
    ${pedidos.length === 0 && html`<p class="vazio">Nenhum pedido ainda. Escolha no cardápio e envie para a cozinha.</p>`}
    ${pedidos.map((p) => html`<article key=${p.id} class="pedido-cliente">
      <header><h3>Pedido das ${hora(p.criado_em)}</h3><span class="pedido-valor">${reais(p.total)}</span></header>
      <${Andamento} status=${p.status} />
      <${ItensPedido} itens=${p.itens} />
    </article>`)}
    ${pedidos.length > 0 && html`<p class="conta-parcial"><span>Consumo até agora</span><strong>${reais(mesa.subtotal)}</strong></p>`}
    <div class="chamados">
      ${mesa.chamado && html`<p class="chamado-ativo"><${Icone} nome="sino" tamanho=${18} />
        ${mesa.chamado === 'conta' ? 'Conta pedida. Um garçom está a caminho.' : 'Garçom chamado. Ele já vem.'}</p>`}
      <button class="botao botao-contorno" disabled=${chamando || mesa.chamado === 'garcom'}
        onClick=${() => chamar('garcom')}>Chamar garçom</button>
      <button class="botao botao-contorno" disabled=${chamando || mesa.chamado === 'conta' || pedidos.length === 0}
        onClick=${() => chamar('conta')}>Pedir a conta</button>
    </div>
  <//>`;
}

function Cliente() {
  const cardapio = useDados('/api/cardapio', ['cardapio']);
  const mesa = useDados(`/api/mesa/${MESA}`, ['pedidos', 'mesas']);
  const carrinho = useCarrinho(`lagiovanna-carrinho-mesa-${MESA}`);
  const [folha, setFolha] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async () => {
    setEnviando(true);
    try {
      await api(`/api/mesa/${MESA}/pedidos`, { metodo: 'POST', corpo: { itens: carrinho.paraEnvio() } });
      carrinho.limpar();
      await mesa.recarregar();
      setFolha('pedidos');
      avisar('Pedido enviado para a cozinha');
    } catch (e) {
      avisar(e.message, 'erro');
      if (e.status === 409) cardapio.recarregar();
    }
    setEnviando(false);
  };

  const emAndamento = mesa.dados ? mesa.dados.pedidos.filter((p) => ['pendente', 'preparo', 'pronto'].includes(p.status)).length : 0;

  return html`<div class="cliente">
    <header class="cliente-topo azulejo">
      <div class="bandeira" aria-hidden="true"></div>
      <div class="cliente-topo-linha">
        <${Letreiro} classe="letreiro-placa" />
        <p class="mesa-prato" aria-label="Você está na mesa ${mesa2(MESA)}"><span>Mesa</span><strong>${mesa2(MESA)}</strong></p>
      </div>
    </header>

    <main class="cliente-corpo">
      ${cardapio.erro && !cardapio.dados && html`<div class="vazio">
        <p>${cardapio.erro}</p>
        <button class="botao botao-contorno" onClick=${cardapio.recarregar}>Tentar de novo</button>
      </div>`}
      ${!cardapio.dados && !cardapio.erro && html`<p class="carregando">Abrindo o cardápio…</p>`}
      ${cardapio.dados && html`<${Cardapio} cardapio=${cardapio.dados} carrinho=${carrinho} />`}
      <p class="rodape-privacidade">Não pedimos seu nome, telefone ou CPF para fazer o pedido.
        <a href="/privacidade">Aviso de privacidade</a></p>
    </main>

    <div class="barra-pedido">
      <button class="botao botao-contorno barra-pedido-meus" onClick=${() => setFolha('pedidos')}>
        Meus pedidos${emAndamento > 0 && html`<span class="contador">${emAndamento}</span>`}
      </button>
      <button class="botao botao-primario barra-pedido-ver" disabled=${carrinho.quantidade === 0}
        onClick=${() => setFolha('carrinho')}>
        ${carrinho.quantidade === 0
          ? 'Seu pedido está vazio'
          : html`Ver pedido (${carrinho.quantidade}) <span class="botao-valor">${reais(carrinho.total)}</span>`}
      </button>
    </div>

    ${folha === 'carrinho' && html`<${FolhaCarrinho} carrinho=${carrinho} titulo="Seu pedido"
      textoEnviar="Enviar para a cozinha" enviando=${enviando} aoEnviar=${enviar} aoFechar=${() => setFolha(null)} />`}
    ${folha === 'pedidos' && mesa.dados && html`<${MeusPedidos} mesa=${mesa.dados} recarregar=${mesa.recarregar}
      aoFechar=${() => setFolha(null)} />`}
  </div>`;
}

iniciar(Cliente);
