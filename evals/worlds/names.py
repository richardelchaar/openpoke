"""Name lists for the generated worlds.

The dev and held-out worlds draw the people that cases are about from separate lists.
Filler people never share a first name or surname with them, so adding filler to a
roster can't change the right answer to a case. Half the filler uses near-miss names
(Mara for Maria, Parks for Park) so the roster still looks crowded around the real ones.
"""

from __future__ import annotations

CORE_FIRST = {
    "dev": """Maria Daniel Priya Omar Hannah Victor Leila Marcus Sofia Ethan Nadia Julian Carmen Tobias Ingrid
        Rafael Amara Colin Yuki Desmond Elena Farid Greta Hassan Imani Jonas Keiko Lorenzo Mina Nikolai
        Olivia Pavel Renee Samir Tessa Umar Vera Wesley Ximena Yusuf Zara Anton Bianca Caleb Dalia
        Emeka Fiona Gustavo Helga Ivan Jasmine Kofi Lucia Mateo Noor Oscar Paloma Quentin Rosa Stefan
        Thea Uri Valentina Winston Yara Zoran Astrid Bruno Celeste Dmitri Esme Felix Gia Hugo""".split(),
    "heldout": """Abigail Bashir Chiara Devon Eleni Finn Gabriela Hamza Isla Jamal Katya Liam Maren Nasser Odette
        Pedro Rania Soren Talia Usman Viola Warren Xavier Yasmin Zeke Adele Boris Camille Darius Edith
        Fabian Grace Henrik Ines Joaquin Kira Leon Maya Nils Opal Piotr Ruth Silas Tamar Ulrich
        Vivian Wade Yolanda Zain Anika Bram Cora Dev Elise Frank Gwen Harlan Irene Jude Kamal
        Lena Miles Nora Otto Pia Reza Sasha Theo Una Vince Willa Yann Zelda Arlo Bea""".split(),
}

CORE_LAST = {
    "dev": """Okafor Lindqvist Marchetti Tanaka Abdullah Brennan Castellano Dvorak Eriksen Fontaine Galvez
        Haddad Ibarra Jankowski Kaplan Laurent Mbeki Novak Oyelaran Petrov Quigley Rossi Sandhu Takahashi
        Ueda Valdez Whitlock Yilmaz Zubiri Achterberg Bellamy Coutinho Delacroix Eastman Farouk Greenwood
        Holloway Iyer Jurado Kessler Lachance Montague Nakamura Ostrowski Pacheco Radcliffe Sorensen
        Thibault Underhill Vasquez Winterbourne Yamamoto Zielinski Ashworth Baptiste Corrigan Dhillon
        Engstrom Fairbanks Gallagher Hutchins Ivanov Jorgensen Kowalczyk Lombardi Mwangi Nordstrom
        Oduya Pemberton Romanov Saldanha Tremblay Ulloa Venter Wojcik Yeboah Zamora Arkwright Bjork
        Cavanagh Desrosiers Elizondo Fukuda Grimaldi Hosseini Inoue Jablonski Kaur Lindahl Morales Nnamdi
        Obrien Pellegrino Rahimi Schreiber Trujillo Vukovic Wainwright Zhou Amsel Bouchard Cisneros Dragan
        Ekwueme Fabbri Gorski Hyland""".split(),
    "heldout": """Adeyemi Blackwood Carvalho Demir Ellsworth Figueroa Gunnarsson Hakimi Iglesias Janssen Kimura
        Lefebvre Mancini Nwosu Olsen Papadakis Qureshi Reinholt Stavros Toussaint Uchida Villanueva Wexler
        Yoon Zapata Aldridge Bergstrom Cardoso Drummond Elmasry Fitzroy Goldberg Halvorsen Idowu Jaramillo
        Kovac Lindgren Moreau Niemi Okonkwo Prescott Ramos Salazar Tiwari Urquhart Vandenberg Westbrook
        Yardley Zeller Appleton Bianchi Calloway Dimitrov Espinoza Fenwick Gupta Hirsch Ishikawa Juarez
        Karlsson Lachapelle Mendez Nyberg Ortega Pohl Rasmussen Sinclair Tavares Ustinov Vogel Whitaker
        Yanez Zimmer Albrecht Boateng
        Castellanos Dossou Ebrahimi Falk Grigoryan Hoekstra Imamura Joshi Kristiansen Leclerc Mahlangu Navarro
        Oyama Pichler Rautio Sokolov Thackeray Udoka Vasiliev Wyndham Zanetti Alvarado Brandt Chowdhury
        Duarte Eze Friedman Gashi Honda""".split(),
}

# Near misses for the names above: close enough to crowd a list, different enough to be
# a different person.
NEAR_FIRST = """Mara Marie Danielle Dane Priyanka Omari Hanna Viktor Layla Marco Sophie Ethel Nadine Julia Carmela
    Toby Inga Raphael Amari Colleen Yuko Desiree Elaine Faris Gretchen Hasan Iman Jonah Keith Loren Minna Nikolas
    Olive Paul Rene Sameer Tess Umair Verna Wes Xena Yousef Zahra Antonia Bianka Kaleb Dahlia
    Abby Basil Clara Devin Elena Finley Gabriel Hamid Isla-Mae Jamie Katia Lian Marin Nasir Odessa
    Pedra Rana Soraya Tal Usama Violet Warrick Xavi Yasmine Zach""".split()

NEAR_LAST = """Okoro Lindgren-Hall Marchetta Tanabe Abdallah Brennon Castello Dvorsky Erikson Fontana Galvan
    Hadad Ibanez Jankovic Kaplin Laurence Mbele Novack Oyelowo Petrova Quigg Rossetti Sandu Takeda
    Uehara Valdes Whitley Yildiz Zubair Bellamont Coutts Delacruz Eastwood Faruk Greenway
    Adeyinka Blackwell Carvalhal Demirci Ellis Figueras Gunnar Hakim Iglesia Jansen Kimoto
    Lefevre Mancuso Nwoye Olson Papadopoulos Qureshy Reinhardt Stavrou Toussant""".split()

FILL_FIRST = """Alden Brigid Corwin Delphine Emmett Fenella Garrick Henrietta Ignatius Jocelyn Kendrick Leopold Marguerite Nathaniel Ottilie Phineas Rosalind Sylvester Theodora Ulysses Winifred Barnaby Clementine Dashiell Eudora Fitzgerald Gwendolyn Horatio Isadora Jethro Lavinia Montgomery Octavia Percival Rowena Thaddeus Wilhelmina Ambrose Cordelia Ezekiel
    Aaron Ian Kurt Lois Nell Owen Ada Bert Cleo Dirk Enid Gail Iris Joel
    Lyle Ora Seth Tina Vern Wanda Alan Brenda Craig Doris Edgar Frieda Gordon Heidi
    Irving Janet Kevin Linda Morris Nancy Orville Patsy Roger Sheila Trevor Ursula Vaughn Wilma
    Arthur Bonnie Clyde Darlene Eugene Florence George Harriet Isaac Judith Kenneth Lorraine Maurice Norma
    Percy Rhonda Stuart Thelma""".split()

FILL_LAST = """Abernathy Blankenship Castleberry Dunleavy Etheridge Featherstone Grantham Hollingsworth Inglewood Kensington Loughlin Macready Netherton Oglethorpe Penhaligon Ravenscroft Stanhope Tattersall Villiers Wetherby Ainsworth Bridgewater Chamberlain Dunmore Eddington Fotheringham Galloway Harrington Kilpatrick Lockhart
    Abbott Dalton Emerson Fletcher Harmon Ingram Jarvis Keller Lawson Norris Osborne Reeves Thornton Upton
    Vance Walton Yates Baxter Dawson Ellison Gibson Irwin Jensen Logan Owens Vaughan York Atkins
    Ewing Ives Kerr Neal Orr Tate Vick Ayers Eaton Judd Nix Odom Pratt Voss
    Ashby Blythe Dodd Estes Flynn""".split()

MAIL_DOMAINS = ["gmail.com", "outlook.com", "icloud.com", "proton.me", "yahoo.ca", "fastmail.com"]
WORK_DOMAINS = {
    "vendor": ["northside-supply.ca", "brightline.io", "harbourworks.ca", "keystone-services.com", "maplegrid.co"],
    "colleague": ["lakeshorebrokers.ca"],
    "adjuster": ["meridianmutual.ca", "coastalassurance.ca"],
}
