// Peças compartilhadas por todas as telas: API, eventos em tempo real, carrinho, cardápio e montador de pizza.
import { html, render, useState, useEffect, useRef, useMemo, useCallback } from '../vendor/preact-htm.js';

export { html, render, useState, useEffect, useRef, useMemo, useCallback };

// ---------- Formatação ----------

export const reais = (centavos) => (centavos / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
export const mesa2 = (numero) => String(numero).padStart(2, '0');
export const hora = (texto) => (texto ? texto.slice(11, 16) : '');
export const paraData = (texto) => new Date(texto.replace(' ', 'T'));
export const minutosDesde = (texto) => Math.max(0, Math.floor((Date.now() - paraData(texto).getTime()) / 60000));
export const tempoDecorrido = (texto) => {
  const min = minutosDesde(texto);
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)}h${String(min % 60).padStart(2, '0')}`;
};
export const paraCentavos = (texto) => {
  const numero = parseFloat(String(texto).replace(/[^\d,]/g, '').replace(',', '.'));
  return Number.isFinite(numero) ? Math.round(numero * 100) : 0;
};
export const centavosParaTexto = (centavos) => (centavos / 100).toFixed(2).replace('.', ',');
export const semAcento = (texto) => texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export const ROTULO_STATUS = {
  pendente: 'Recebido', preparo: 'Em preparo', pronto: 'Pronto', entregue: 'Na mesa', cancelado: 'Cancelado',
};
export const ROTULO_PAGAMENTO = { dinheiro: 'Dinheiro', pix: 'Pix', credito: 'Crédito', debito: 'Débito' };

// ---------- API ----------

export class ErroApi extends Error {
  constructor(mensagem, status) { super(mensagem); this.status = status; }
}

export async function api(caminho, { metodo = 'GET', corpo, form } = {}) {
  const opcoes = { method: metodo, headers: {}, credentials: 'same-origin' };
  if (form) opcoes.body = form;
  else if (corpo !== undefined) {
    opcoes.headers['Content-Type'] = 'application/json';
    opcoes.body = JSON.stringify(corpo);
  }
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch {
    throw new ErroApi('Sem conexão com a pizzaria. Confira a internet e tente de novo.', 0);
  }
  let dados = null;
  try { dados = await resposta.json(); } catch { /* resposta sem corpo */ }
  if (!resposta.ok) {
    if (resposta.status === 401 && window.DADOS?.usuario) {
      location.href = '/entrar?proximo=' + encodeURIComponent(location.pathname);
    }
    throw new ErroApi(dados?.erro || 'Algo deu errado. Tente de novo.', resposta.status);
  }
  return dados;
}

// ---------- Tempo real ----------

const ouvintes = new Set();
let fonte = null;
let jaConectou = false;

function conectarEventos() {
  if (fonte) return;
  fonte = new EventSource('/api/eventos');
  fonte.onmessage = (evento) => ouvintes.forEach((ouvinte) => ouvinte(evento.data));
  // Ao reconectar depois de uma queda, recarrega tudo: algum evento pode ter se perdido.
  fonte.onopen = () => { if (jaConectou) ouvintes.forEach((o) => o('*')); jaConectou = true; };
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) ouvintes.forEach((o) => o('*'));
  });
}

export function useEventos(tipos, acao) {
  const ref = useRef(acao);
  ref.current = acao;
  useEffect(() => {
    conectarEventos();
    const ouvinte = (tipo) => { if (tipo === '*' || tipos.includes(tipo)) ref.current(tipo); };
    ouvintes.add(ouvinte);
    return () => ouvintes.delete(ouvinte);
  }, []);
}

export function useDados(caminho, tipos = []) {
  const [estado, setEstado] = useState({ dados: null, erro: null });
  const sequencia = useRef(0);
  const recarregar = useCallback(async () => {
    if (!caminho) return;
    const numero = ++sequencia.current;
    try {
      const dados = await api(caminho);
      if (numero === sequencia.current) setEstado({ dados, erro: null });
    } catch (erro) {
      if (numero === sequencia.current) setEstado((atual) => ({ dados: atual.dados, erro: erro.message }));
    }
  }, [caminho]);
  useEffect(() => { setEstado({ dados: null, erro: null }); recarregar(); }, [recarregar]);
  useEventos(tipos, recarregar);
  return { ...estado, recarregar };
}

/** Força um novo desenho a cada intervalo, para os relógios das telas andarem. */
export function useRelogio(segundos = 30) {
  const [, setTique] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTique((t) => t + 1), segundos * 1000);
    return () => clearInterval(id);
  }, [segundos]);
}

// ---------- Avisos ----------

let publicarAviso = () => {};
export const avisar = (texto, tipo = 'ok') => publicarAviso({ texto, tipo, id: Date.now() + Math.random() });

export function Avisos() {
  const [lista, setLista] = useState([]);
  useEffect(() => {
    publicarAviso = (aviso) => {
      setLista((atual) => [...atual.slice(-2), aviso]);
      setTimeout(() => setLista((atual) => atual.filter((a) => a.id !== aviso.id)), aviso.tipo === 'erro' ? 6000 : 3200);
    };
  }, []);
  return html`<div class="avisos" role="status" aria-live="polite">
    ${lista.map((a) => html`<div key=${a.id} class="aviso-flutuante aviso-${a.tipo}">${a.texto}</div>`)}
  </div>`;
}

// ---------- Ícones ----------

const TRACOS = {
  mais: 'M12 5v14M5 12h14',
  menos: 'M5 12h14',
  fechar: 'M6 6l12 12M18 6L6 18',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  voltar: 'M15 5l-7 7 7 7',
  lixeira: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  lapis: 'M4 20h4L19 9l-4-4L4 16v4zM13 7l4 4',
  sino: 'M6 16V11a6 6 0 1112 0v5l2 2H4l2-2zM10 21h4',
  relogio: 'M12 7v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z',
  sair: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
  busca: 'M11 4a7 7 0 100 14 7 7 0 000-14zM16.5 16.5L21 21',
  recibo: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6',
  copiar: 'M9 9h11v11H9zM5 15H4V4h11v1',
  som: 'M4 9v6h4l5 4V5L8 9H4zM16 9a4 4 0 010 6',
  cima: 'M6 15l6-6 6 6',
  baixo: 'M6 9l6 6 6-6',
};

export function Icone({ nome, tamanho = 20 }) {
  return html`<svg class="icone" width=${tamanho} height=${tamanho} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d=${TRACOS[nome]} /></svg>`;
}

export function Letreiro({ classe = '' }) {
  return html`<div class="letreiro ${classe}">
    <span class="letreiro-sub">Pizzaria e Cafeteria</span>
    <span class="letreiro-nome">La Giovanna</span>
  </div>`;
}

// ---------- Folha (painel que sobe no celular, janela no computador) ----------

export function Folha({ titulo, aoFechar, children, rodape, classe = '' }) {
  const ref = useRef(null);
  useEffect(() => {
    const anterior = document.activeElement;
    document.body.classList.add('sem-rolagem');
    ref.current?.focus();
    const tecla = (e) => { if (e.key === 'Escape') aoFechar(); };
    document.addEventListener('keydown', tecla);
    return () => {
      document.removeEventListener('keydown', tecla);
      setTimeout(() => {
        if (!document.querySelector('.folha-fundo')) document.body.classList.remove('sem-rolagem');
      });
      anterior?.focus?.();
    };
  }, []);
  return html`<div class="folha-fundo" onMouseDown=${(e) => { if (e.target === e.currentTarget) aoFechar(); }}>
    <section class="folha ${classe}" role="dialog" aria-modal="true" aria-label=${titulo} tabindex="-1" ref=${ref}>
      <header class="folha-topo">
        <h2>${titulo}</h2>
        <button class="botao-icone" onClick=${aoFechar} aria-label="Fechar"><${Icone} nome="fechar" /></button>
      </header>
      <div class="folha-corpo">${children}</div>
      ${rodape && html`<footer class="folha-rodape">${rodape}</footer>`}
    </section>
  </div>`;
}

export function Quantidade({ valor, aoMudar, minimo = 0, rotulo = 'item' }) {
  return html`<div class="quantidade">
    <button type="button" onClick=${() => aoMudar(valor - 1)} disabled=${valor <= minimo}
      aria-label="Tirar um ${rotulo}"><${Icone} nome="menos" tamanho=${18} /></button>
    <output aria-live="polite">${valor}</output>
    <button type="button" onClick=${() => aoMudar(valor + 1)} disabled=${valor >= 20}
      aria-label="Colocar mais um ${rotulo}"><${Icone} nome="mais" tamanho=${18} /></button>
  </div>`;
}

// ---------- Carrinho ----------

export function useCarrinho(chave) {
  const [itens, setItens] = useState(() => {
    try { return JSON.parse(localStorage.getItem(chave)) || []; } catch { return []; }
  });
  useEffect(() => {
    try { localStorage.setItem(chave, JSON.stringify(itens)); } catch { /* armazenamento indisponível */ }
  }, [itens]);

  return useMemo(() => ({
    itens,
    total: itens.reduce((soma, i) => soma + i.preco * i.quantidade, 0),
    quantidade: itens.reduce((soma, i) => soma + i.quantidade, 0),
    quantidadeDe: (produtoId) => itens.filter((i) => i.produto_id === produtoId && !i.montado)
      .reduce((soma, i) => soma + i.quantidade, 0),
    adicionar(item) {
      setItens((atual) => {
        const igual = !item.montado && atual.find((i) => !i.montado && i.produto_id === item.produto_id && !i.observacao);
        if (igual) return atual.map((i) => (i === igual ? { ...i, quantidade: Math.min(20, i.quantidade + item.quantidade) } : i));
        return [...atual, { ...item, uid: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}` }];
      });
    },
    mudarQuantidade(uid, quantidade) {
      setItens((atual) => (quantidade <= 0
        ? atual.filter((i) => i.uid !== uid)
        : atual.map((i) => (i.uid === uid ? { ...i, quantidade: Math.min(20, quantidade) } : i))));
    },
    tirarUmDe(produtoId) {
      setItens((atual) => {
        const alvo = [...atual].reverse().find((i) => i.produto_id === produtoId && !i.montado);
        if (!alvo) return atual;
        return alvo.quantidade <= 1
          ? atual.filter((i) => i !== alvo)
          : atual.map((i) => (i === alvo ? { ...i, quantidade: i.quantidade - 1 } : i));
      });
    },
    observar(uid, observacao) {
      setItens((atual) => atual.map((i) => (i.uid === uid ? { ...i, observacao } : i)));
    },
    limpar() { setItens([]); },
    paraEnvio: () => itens.map((i) => ({
      produto_id: i.produto_id,
      produto2_id: i.produto2_id ?? null,
      borda_id: i.borda_id ?? null,
      quantidade: i.quantidade,
      observacao: i.observacao || null,
    })),
  }), [itens]);
}

// ---------- Cardápio ----------

export function Cardapio({ cardapio, carrinho, busca = false }) {
  const [montando, setMontando] = useState(null);
  const [termo, setTermo] = useState('');
  const [ativa, setAtiva] = useState(null);
  const secoes = useRef({});

  const categorias = useMemo(() => {
    const alvo = semAcento(termo.trim());
    if (!alvo) return cardapio.categorias;
    return cardapio.categorias
      .map((c) => ({ ...c, produtos: c.produtos.filter((p) => semAcento(p.nome + ' ' + p.descricao).includes(alvo)) }))
      .filter((c) => c.produtos.length);
  }, [cardapio, termo]);

  useEffect(() => {
    const observador = new IntersectionObserver((entradas) => {
      const visivel = entradas.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (visivel) setAtiva(Number(visivel.target.dataset.categoria));
    }, { rootMargin: '-20% 0px -65% 0px' });
    Object.values(secoes.current).forEach((el) => el && observador.observe(el));
    return () => observador.disconnect();
  }, [categorias]);

  const irPara = (id) => {
    setAtiva(id);
    secoes.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return html`<div class="cardapio">
    <nav class="categorias" aria-label="Categorias do cardápio">
      ${busca && html`<label class="busca">
        <${Icone} nome="busca" tamanho=${18} />
        <input type="search" placeholder="Buscar no cardápio" value=${termo} onInput=${(e) => setTermo(e.target.value)}
          aria-label="Buscar no cardápio" />
      </label>`}
      <div class="categorias-lista">
        ${categorias.map((c) => html`<button key=${c.id} type="button"
          class="categoria-atalho ${(ativa ?? categorias[0]?.id) === c.id ? 'ativa' : ''}"
          onClick=${() => irPara(c.id)}>${c.nome}</button>`)}
      </div>
    </nav>

    ${categorias.length === 0 && html`<p class="vazio">Nada encontrado para “${termo}”.</p>`}

    ${categorias.map((c) => html`<section key=${c.id} class="secao-cardapio" data-categoria=${c.id}
        ref=${(el) => { secoes.current[c.id] = el; }}>
      <h2>${c.nome}</h2>
      ${c.tipo === 'pizza' && html`<p class="secao-nota">Pizza grande, 8 fatias. Toque no sabor para escolher
        meio a meio e borda recheada.</p>`}
      <ul class="produtos">
        ${c.produtos.map((p) => html`<${LinhaProduto} key=${p.id} produto=${p} pizza=${c.tipo === 'pizza'}
          carrinho=${carrinho} aoMontar=${() => setMontando(p)} />`)}
      </ul>
    </section>`)}

    ${montando && html`<${MontadorPizza} produto=${montando} cardapio=${cardapio}
      aoFechar=${() => setMontando(null)}
      aoAdicionar=${(item) => { carrinho.adicionar(item); setMontando(null); avisar(`${item.nome} no pedido`); }} />`}
  </div>`;
}

function LinhaProduto({ produto, pizza, carrinho, aoMontar }) {
  const noCarrinho = pizza ? 0 : carrinho.quantidadeDe(produto.id);
  const adicionar = () => carrinho.adicionar({
    produto_id: produto.id, nome: produto.nome, preco: produto.preco, quantidade: 1,
  });
  const texto = html`
    <span class="produto-titulo">
      <span class="produto-nome">${produto.nome}</span>
      <span class="produto-pontos" aria-hidden="true"></span>
      <span class="produto-preco">${reais(produto.preco)}</span>
    </span>
    ${produto.descricao && html`<span class="produto-descricao">${produto.descricao}</span>`}`;

  return html`<li class="produto ${produto.imagem ? 'com-foto' : ''}">
    ${produto.imagem && html`<img class="produto-foto" src=${produto.imagem} alt="" loading="lazy" width="88" height="88" />`}
    ${pizza
      ? html`<button type="button" class="produto-texto produto-toque" onClick=${aoMontar}>${texto}</button>`
      : html`<div class="produto-texto">${texto}</div>`}
    <div class="produto-acao">
      ${pizza && html`<button type="button" class="botao-mais" onClick=${aoMontar}
        aria-label="Montar pizza de ${produto.nome}"><${Icone} nome="mais" /></button>`}
      ${!pizza && noCarrinho === 0 && html`<button type="button" class="botao-mais" onClick=${adicionar}
        aria-label="Adicionar ${produto.nome}"><${Icone} nome="mais" /></button>`}
      ${!pizza && noCarrinho > 0 && html`<${Quantidade} valor=${noCarrinho} rotulo=${produto.nome}
        aoMudar=${(novo) => (novo > noCarrinho ? adicionar() : carrinho.tirarUmDe(produto.id))} />`}
    </div>
  </li>`;
}

// ---------- Montador de pizza ----------

function DesenhoPizza({ metades, borda }) {
  return html`<svg class="desenho-pizza" viewBox="0 0 120 120" aria-hidden="true">
    <circle cx="60" cy="60" r="57" fill="#d9974a" />
    ${borda && html`<circle cx="60" cy="60" r="52.5" fill="none" stroke="#fff1c9" stroke-width="5" stroke-dasharray="3 5" />`}
    <circle cx="60" cy="60" r="47" fill="#f5c451" />
    ${metades && html`<path d="M60 13a47 47 0 010 94z" fill="#e9823a" />
      <path d="M60 11v98" stroke="#fffdf9" stroke-width="3" />`}
    <g fill="#c8201f">
      <circle cx="40" cy="42" r="6" /><circle cx="36" cy="72" r="6" /><circle cx="50" cy="90" r="5" />
    </g>
    <g fill=${metades ? '#0d7a40' : '#c8201f'}>
      <circle cx="80" cy="40" r="6" /><circle cx="86" cy="68" r="6" /><circle cx="72" cy="88" r="5" />
    </g>
  </svg>`;
}

export function MontadorPizza({ produto, cardapio, aoAdicionar, aoFechar }) {
  const [meia, setMeia] = useState(false);
  const [sabor2, setSabor2] = useState(null);
  const [bordaId, setBordaId] = useState(null);
  const [observacao, setObservacao] = useState('');
  const [quantidade, setQuantidade] = useState(1);

  const sabores = useMemo(() => cardapio.categorias.filter((c) => c.tipo === 'pizza')
    .map((c) => ({ ...c, produtos: c.produtos.filter((p) => p.id !== produto.id) }))
    .filter((c) => c.produtos.length), [cardapio, produto]);
  const borda = cardapio.bordas.find((b) => b.id === bordaId);
  const base = meia && sabor2 ? Math.max(produto.preco, sabor2.preco) : produto.preco;
  const unitario = base + (borda ? borda.preco : 0);
  const falta = meia && !sabor2;

  const confirmar = () => aoAdicionar({
    montado: true,
    produto_id: produto.id,
    produto2_id: meia && sabor2 ? sabor2.id : null,
    borda_id: borda ? borda.id : null,
    nome: meia && sabor2 ? `½ ${produto.nome} + ½ ${sabor2.nome}` : produto.nome,
    detalhe: borda ? `Borda ${borda.nome}` : null,
    preco: unitario,
    quantidade,
    observacao: observacao.trim(),
  });

  const rodape = html`
    <${Quantidade} valor=${quantidade} minimo=${1} aoMudar=${setQuantidade} rotulo="pizza" />
    <button type="button" class="botao botao-primario botao-largo" disabled=${falta} onClick=${confirmar}>
      ${falta ? 'Escolha o segundo sabor' : html`Adicionar <span class="botao-valor">${reais(unitario * quantidade)}</span>`}
    </button>`;

  return html`<${Folha} titulo="Monte sua pizza" aoFechar=${aoFechar} rodape=${rodape} classe="folha-montador">
    <div class="montador-topo">
      <${DesenhoPizza} metades=${meia} borda=${!!borda} />
      <div class="montador-resumo">
        <p class="montador-sabor">${meia ? '½ ' : ''}${produto.nome}</p>
        ${meia && html`<p class="montador-sabor ${sabor2 ? '' : 'pendente'}">½ ${sabor2 ? sabor2.nome : 'escolha abaixo'}</p>`}
        ${borda && html`<p class="montador-borda">Borda ${borda.nome}</p>`}
        ${produto.descricao && !meia && html`<p class="montador-descricao">${produto.descricao}</p>`}
      </div>
    </div>

    <fieldset class="grupo">
      <legend>Como você quer?</legend>
      <div class="alternar" role="radiogroup">
        <button type="button" role="radio" aria-checked=${!meia} class=${!meia ? 'ativa' : ''}
          onClick=${() => setMeia(false)}>Inteira</button>
        <button type="button" role="radio" aria-checked=${meia} class=${meia ? 'ativa' : ''}
          onClick=${() => setMeia(true)}>Meio a meio</button>
      </div>
      ${meia && html`<p class="grupo-nota">No meio a meio vale o preço do sabor mais caro.</p>`}
    </fieldset>

    ${meia && html`<fieldset class="grupo">
      <legend>Segundo sabor</legend>
      ${sabores.map((c) => html`<div key=${c.id} class="sabores">
        <p class="sabores-titulo">${c.nome}</p>
        ${c.produtos.map((p) => html`<label key=${p.id} class="opcao">
          <input type="radio" name="sabor2" checked=${sabor2?.id === p.id} onChange=${() => setSabor2(p)} />
          <span class="opcao-nome">${p.nome}</span>
          <span class="opcao-preco">${reais(p.preco)}</span>
        </label>`)}
      </div>`)}
    </fieldset>`}

    ${cardapio.bordas.length > 0 && html`<fieldset class="grupo">
      <legend>Borda</legend>
      <label class="opcao">
        <input type="radio" name="borda" checked=${bordaId === null} onChange=${() => setBordaId(null)} />
        <span class="opcao-nome">Tradicional, sem recheio</span>
      </label>
      ${cardapio.bordas.map((b) => html`<label key=${b.id} class="opcao">
        <input type="radio" name="borda" checked=${bordaId === b.id} onChange=${() => setBordaId(b.id)} />
        <span class="opcao-nome">Recheada de ${b.nome}</span>
        <span class="opcao-preco">+ ${reais(b.preco)}</span>
      </label>`)}
    </fieldset>`}

    <div class="grupo">
      <label class="rotulo" for="obs-pizza">Alguma observação?</label>
      <textarea id="obs-pizza" class="campo" rows="2" maxlength="200" placeholder="Ex.: sem cebola, bem assada"
        value=${observacao} onInput=${(e) => setObservacao(e.target.value)}></textarea>
    </div>
  <//>`;
}

// ---------- Carrinho (folha) ----------

export function FolhaCarrinho({ carrinho, titulo, textoEnviar, enviando, aoEnviar, aoFechar }) {
  const rodape = carrinho.itens.length > 0 && html`
    <button type="button" class="botao botao-primario botao-largo" disabled=${enviando} onClick=${aoEnviar}>
      ${enviando ? 'Enviando…' : html`${textoEnviar} <span class="botao-valor">${reais(carrinho.total)}</span>`}
    </button>`;
  return html`<${Folha} titulo=${titulo} aoFechar=${aoFechar} rodape=${rodape}>
    ${carrinho.itens.length === 0
      ? html`<p class="vazio">Seu pedido está vazio. Escolha algo no cardápio.</p>`
      : html`<ul class="carrinho">
        ${carrinho.itens.map((i) => html`<li key=${i.uid} class="carrinho-item">
          <div class="carrinho-linha">
            <div>
              <p class="carrinho-nome">${i.nome}</p>
              ${i.detalhe && html`<p class="carrinho-detalhe">${i.detalhe}</p>`}
              <p class="carrinho-preco">${reais(i.preco * i.quantidade)}</p>
            </div>
            <${Quantidade} valor=${i.quantidade} rotulo=${i.nome}
              aoMudar=${(q) => carrinho.mudarQuantidade(i.uid, q)} />
          </div>
          <input class="campo campo-obs" maxlength="200" placeholder="Observação (opcional)" value=${i.observacao || ''}
            aria-label="Observação para ${i.nome}" onInput=${(e) => carrinho.observar(i.uid, e.target.value)} />
        </li>`)}
      </ul>`}
  <//>`;
}

// ---------- Pedido (lista de itens com status) ----------

export function ItensPedido({ itens }) {
  return html`<ul class="itens-pedido">
    ${itens.map((i) => html`<li key=${i.id} class=${i.cancelado ? 'cancelado' : ''}>
      <span class="item-qtd">${i.quantidade}×</span>
      <span class="item-texto">
        <span class="item-nome">${i.descricao}</span>
        ${i.detalhe && html`<span class="item-detalhe">${i.detalhe}</span>`}
        ${i.observacao && html`<span class="item-obs">${i.observacao}</span>`}
      </span>
    </li>`)}
  </ul>`;
}

export function Selo({ status }) {
  return html`<span class="selo selo-${status}">${ROTULO_STATUS[status]}</span>`;
}

export function BarraEquipe({ titulo, usuario, children }) {
  const sair = async () => { await api('/api/logout', { metodo: 'POST' }); location.href = '/entrar'; };
  return html`<header class="barra-equipe">
    <div class="barra-marca"><${Letreiro} classe="letreiro-pequeno" /><span class="barra-titulo">${titulo}</span></div>
    <div class="barra-acoes">
      ${children}
      <span class="barra-usuario">${usuario.nome}</span>
      <button class="botao-icone" onClick=${sair} aria-label="Sair" title="Sair"><${Icone} nome="sair" /></button>
    </div>
  </header>`;
}

export function iniciar(Componente) {
  const raiz = document.getElementById('app');
  raiz.innerHTML = '';
  render(html`<${Componente} /><${Avisos} />`, raiz);
}
