\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{resume}[2024/09/22 An elegant Résumé class]
\LoadClass[11pt]{article}

% disable indent globally
\setlength{\parindent}{0pt}
% some general improvements, defines the XeTeX logo
\RequirePackage{xltxtra}
% use xifthen
\RequirePackage{xifthen}
% use hyperlink for email and url
\RequirePackage{hyperref}
\hypersetup{hidelinks}
\RequirePackage{url}
\urlstyle{tt}

% use fontawesome6
\RequirePackage{stys/fontawesome6}

% use xcolor for customizing color
\RequirePackage{xcolor}
%% Color setup
\definecolor{cyanbg}{HTML}{f0fafa}
\definecolor{cyanfg}{HTML}{00a6a7}
\definecolor{nwpubluebg}{HTML}{01408f}
% \definecolor{nwpubluebg}{HTML}{004DFF} % C100 M70

% loading fonts
\RequirePackage{fontspec}
% Main document font
\setmainfont[
  Path = fonts/Main/ ,
  Extension = .otf ,
  UprightFont = *-regular ,
  BoldFont = *-bold ,
  ItalicFont = *-italic ,
  BoldItalicFont = *-bolditalic ,
  SmallCapsFont = Fontin-SmallCaps
]{texgyretermes}

\RequirePackage[
	a4paper,
	left=0.80in,
	right=0.80in,
	top=0.85in, % tune this!
	bottom=0.55in,
	nohead
]{geometry}

\RequirePackage{titlesec}
\RequirePackage{enumitem}
\setlist{noitemsep} % removes spacing from items but leaves space around the whole list
%\setlist{nosep} % removes all vertical spacing within and around the list
\setlist[itemize]{topsep=0.25em, leftmargin=1.25pc}
\setlist[enumerate]{topsep=0.25em, leftmargin=1.25pc}
\RequirePackage[super]{nth}

\newcommand{\titlelinestyle}{default} % partialbg, fullbg
\newcommand{\settitlelinestyle}[1]{%
  \renewcommand{\titlelinestyle}{#1}%
  \applyColorAndTitleStyle%
}

\newcommand*{\tallphantom}[1]{\vphantom{\rule{0pt}{#1}}}

\newcommand{\applyColorAndTitleStyle}{%
  \ifthenelse{\equal{\titlelinestyle}{default}}{%
    \colorlet{fgcolor}{nwpubluebg} %
    \colorlet{accentcolor}{nwpubluebg} %
    \titleformat{\section}         % Customise the \section command 
      {\Large\bfseries\raggedright\color{fgcolor}} % Make the \section headers large (\Large),
                                   % small capitals (\scshape) -> bold font (\bfseries),
                                   % left aligned (\raggedright) and use fgcolor
      {}{0em}                      % Can be used to give a prefix to all sections, like 'Section ...'
      {}                           % Can be used to insert code before the heading
      % {\colorbox{fgcolor}{\makebox[0.1em][l]{\strut\tallphantom{16pt}}}} % 有 icon 没必要用这个
      [\titleline{\color{fgcolor}\titlerule}] % Default inserts a horizontal line after the heading
      % REF: https://tex.stackexchange.com/a/40089
  }{%
    \colorlet{bgcolor}{cyanbg}
    \colorlet{fgcolor}{cyanfg}
    \colorlet{accentcolor}{black}
    \ifthenelse{\equal{\titlelinestyle}{partialbg}}{%
      \titleformat{\section}
        {\Large\bfseries\raggedright\color{fgcolor}}
        {}{0em}%
        {}
        [\titleline{\color{fgcolor}\titlerule}]
    }{%
      \ifthenelse{\equal{\titlelinestyle}{fullbg}}{%
        \titleformat{\section}
          {\Large\bfseries\raggedright\color{fgcolor}}
          {}{0em}
          {}
      }{%
          \PackageError{resume}{Invalid value for titlelinestyle: \titlelinestyle}{}
      }%
    }
  }
}
\AtBeginDocument{\applyColorAndTitleStyle}

\titlespacing*{\section}{0cm}{*1.8}{*1.8}

\titleformat{\subsection}
  {\large\raggedright}
  {}{0em}
  {}
\titlespacing*{\subsection}{0cm}{*1.8}{*0.6}

\newcommand{\datedsection}[2]{%
  \section[#1]{#1 \hfill #2}%
}
\newcommand{\datedsubsection}[2]{%
  \subsection[#1]{#1 \hfill #2}%
}
\newcommand{\datedline}[2]{%
  {\par #1 \hfill #2 \par}%
}

\newcommand{\name}[1]{
  \centerline{\Huge\bfseries{#1}}
  \vspace{1.5ex}
}

% defines one's name
% usage: \name{<name>}
\newcommand{\nameTest}[1]{
  {\large\bfseries{#1}}
}

% Title
\newcommand*{\sectionTitle}[2]{%
  \ifthenelse{\equal{\titlelinestyle}{default}}{%
    \section{%
      \texorpdfstring%
        {\icon{#2} #1}% 标题无背景色 有下划线
        {#1}%
    }%
  }{%
    \ifthenelse{\equal{\titlelinestyle}{partialbg}}{%
      \section{%
        \texorpdfstring%
          % {\colorbox{bgcolor}{\color{fgcolor}{\icon{#2} #1}\strut\tallphantom{16pt}}}% 上下 pad
          {\colorbox{bgcolor}{\icon{#2} #1}}% 标题内容部分背景色 可加下划线
          {#1}%
      }%
    }{%
      \ifthenelse{\equal{\titlelinestyle}{fullbg}}{%
        \section{%
          \texorpdfstring%
            % 可以试试 makebox 置顶放 + tallphantom
            % {\colorbox{bgcolor}{\makebox[\textwidth - 6pt][l]{\icon{#2} #1}\strut\tallphantom{16pt}}}%
            {\colorbox{bgcolor}{\makebox[\textwidth - 6pt][l]{\icon{#2} #1}}}% 标题整行背景色 不要加下划线
            {#1}%
        }%
      }{%
          \PackageError{resume}{Invalid value for titlelinestyle: \titlelinestyle}{}
      }%
    }
  }
}

% REF: [resume/resume.cls at master · liweitianux/resume](https://github.com/liweitianux/resume/blob/master/resume.cls)
\def\@iconsize{\normalsize}
\newcommand*{\iconsize}[1]{\def\@iconsize{#1}}

% icon 不设定 size 和 color 在其外层设定
\newcommand*{\icon}[1]{%
  % {\@iconsize{\large}\makebox[1em][c]{\textcolor{fgcolor}{#1}}}%
  {\makebox[1em][c]{#1}}%
  \hspace{0.3em}%\strut%
}

% defines one's email
% usage: \email{<email>}
\newcommand{\email}[1]{\basicInfoItem{\faiconsixbf{envelope}}{\href{mailto:#1}{#1}}}

% defines one's phone
% usage: \phone{<phone>}
\newcommand{\phone}[1]{\basicInfoItem{\faiconsixbf{phone}}{#1}}

\newcommand{\code}[1]{\basicInfoItem{\faiconsixbf{code}}{#1}}

\newcommand{\identity}[1]{\basicInfoItem{\faiconsixbf{address-card}}{#1}}

% also: calendar-days, calendar-week, calendar-minus, calendar-plus
\newcommand{\calendar}[1]{\basicInfoItem{\faiconsixbf{calendar}}{#1}}

\newcommand{\birthday}[1]{\basicInfoItem{\faiconsixbf{cake-candles}}{#1}}

\newcommand{\hometown}[1]{\basicInfoItem{\faiconsixbf{house}}{#1}}

\newcommand{\boy}{\basicInfoItem{\faiconsixbf{mars}}{男}}
\newcommand{\girl}{\basicInfoItem{\faiconsixbf{venus}}{女}}

% defines one's linkedin
% usage: \linkedin{<linkedin>}
\newcommand{\linkedin}[2][]{\basicInfoItem{\faiconsix{linkedin-in}}
  {\ifthenelse{\isempty{#1}}%
    {\href{#2}{#2}}
    {\href{#2}{#1}}}}
\newcommand{\linkedinsquare}[2][]{\basicInfoItem{\faiconsix{linkedin}}
  {\ifthenelse{\isempty{#1}}%
    {\href{#2}{#2}}
    {\href{#2}{#1}}}}

% defines one's GitHub
% usage: \github{<github>}
\newcommand{\github}[2][]{\basicInfoItem{\faiconsix{github}}
  {\ifthenelse{\isempty{#1}}%
    {\href{#2}{#2}}
    {\href{#2}{#1}}}}

% defines one's homepage
% usage: \homepage{<homepage>}
\newcommand{\homepage}[2][]{\basicInfoItem{\faiconsixbf{link}}
  {\ifthenelse{\isempty{#1}}%
    {\href{#2}{#2}}
    {\href{#2}{#1}}}}

% \newcommand{\basicInfoItem}[2]{\color{fgcolor}{\icon{#1}}\ \color{black}\rmfamily\large{#2}}
\newcommand{\basicInfoItem}[2]{\icon{#1}\ \rmfamily\large{#2}}

\newcommand{\dotSep}{\ \ \textbf{\textperiodcentered}\ \ }

\newcommand{\basicInfo}[1]{
  % \centerline{\sffamily\large{#1}}
  \centerline{#1}
  \vspace{1.5ex}
}

\newcommand{\role}[2]{
  {\par \textit{#1} ~ #2 \par}
  \vspace{0.6ex}
}

\newcommand{\texthl}[1]{\textcolor{accentcolor}{\textbf{#1}}}

\newcommand{\normalline}[1]{\par #1 \par}
