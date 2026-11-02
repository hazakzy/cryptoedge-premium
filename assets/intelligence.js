/* Render public highlights as text. No private research or auth state. */
(function(){
  var host=document.querySelector('[data-intelligence-feed]');
  if(!host)return;
  var archive=host.getAttribute('data-intelligence-feed')==='highlights';
  var state=host.querySelector('[data-feed-state]');
  var contents=host.querySelector('[data-feed-content]');
  function element(tag,className,text){var e=document.createElement(tag);if(className)e.className=className;if(text)e.textContent=text;return e;}
  function stamp(value){var date=new Date(value);if(!Number.isFinite(date.getTime()))return 'Recent edition';return new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:false}).format(date);}
  fetch('/api/intelligence?limit='+(archive?'7':'1')).then(function(response){if(!response.ok)throw Error('Unavailable');return response.json();}).then(function(data){
    if(!Array.isArray(data.briefs))throw Error('Invalid response');
    if(!data.briefs.length){state.textContent='The first highlights will appear here when published. Follow the public channel for updates.';return;}
    state.textContent='Free to read · Latest '+stamp(data.briefs[0].as_of);
    data.briefs.forEach(function(brief,index){
      var article=element(archive&&index?'details':'article','published-brief');
      var heading=element(archive&&index?'summary':'h3','',brief.title);
      article.appendChild(heading);article.appendChild(element('p','brief-date',stamp(brief.as_of)));
      if(archive){article.appendChild(element('div','brief-body',brief.highlights));var channel=element('a','quiet-link','Read the full free brief on Telegram ↗');channel.href='https://t.me/cryptoedgelab';channel.target='_blank';channel.rel='noopener noreferrer';article.appendChild(channel);}
      else{article.appendChild(element('p','',brief.preview));var link=element('a','quiet-link','Read the highlights →');link.href='/intelligence.html#latest';article.appendChild(link);}
      contents.appendChild(article);
    });
    contents.hidden=false;
  }).catch(function(){state.textContent='The latest brief is temporarily unavailable here. You can check the public Telegram channel.';});
})();
