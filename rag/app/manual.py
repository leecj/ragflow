import copy
import re

from api.db import ParserType
from rag.nlp import huqie, tokenize, tokenize_table, add_positions
from deepdoc.parser import PdfParser
from rag.utils import num_tokens_from_string


class Pdf(PdfParser):
    def __init__(self):
        self.model_speciess = ParserType.MANUAL.value
        super().__init__()

    def __call__(self, filename, binary=None, from_page=0,
                 to_page=100000, zoomin=3, callback=None):
        callback(msg="OCR is  running...")
        self.__images__(
            filename if not binary else binary,
            zoomin,
            from_page,
            to_page,
            callback
        )
        callback(msg="OCR finished.")

        from timeit import default_timer as timer
        start = timer()
        self._layouts_rec(zoomin)
        callback(0.65, "Layout analysis finished.")
        print("paddle layouts:", timer() - start)
        self._table_transformer_job(zoomin)
        callback(0.67, "Table analysis finished.")
        self._text_merge()
        self._concat_downward(concat_between_pages=False)
        self._filter_forpages()
        callback(0.68, "Text merging finished")
        tbls = self._extract_table_figure(True, zoomin, True, True)

        # clean mess
        for b in self.boxes:
            b["text"] = re.sub(r"([\t 　]|\u3000){2,}", " ", b["text"].strip())

        # merge chunks with the same bullets
        self._merge_with_same_bullet()

        # merge title with decent chunk
        i = 0
        while i + 1 < len(self.boxes):
            b = self.boxes[i]
            if b.get("layoutno","").find("title") < 0:
                i += 1
                continue
            b_ = self.boxes[i + 1]
            b_["text"] = b["text"] + "\n" + b_["text"]
            b_["x0"] = min(b["x0"], b_["x0"])
            b_["x1"] = max(b["x1"], b_["x1"])
            b_["top"] = b["top"]
            self.boxes.pop(i)

        callback(0.8, "Parsing finished")
        for b in self.boxes: print(b["text"], b.get("layoutno"))

        print(tbls)
        return [b["text"] + self._line_tag(b, zoomin) for b in self.boxes], tbls


def chunk(filename, binary=None, from_page=0, to_page=100000, lang="Chinese", callback=None, **kwargs):
    """
        Only pdf is supported.
    """
    pdf_parser = None

    if re.search(r"\.pdf$", filename, re.IGNORECASE):
        pdf_parser = Pdf()
        cks, tbls = pdf_parser(filename if not binary else binary,
                           from_page=from_page, to_page=to_page, callback=callback)
    else: raise NotImplementedError("file type not supported yet(pdf supported)")
    doc = {
        "docnm_kwd": filename
    }
    doc["title_tks"] = huqie.qie(re.sub(r"\.[a-zA-Z]+$", "", doc["docnm_kwd"]))
    doc["title_sm_tks"] = huqie.qieqie(doc["title_tks"])
    # is it English
    eng = lang.lower() == "english"#pdf_parser.is_english

    res = tokenize_table(tbls, doc, eng)

    i = 0
    chunk = []
    tk_cnt = 0
    def add_chunk():
        nonlocal chunk, res, doc, pdf_parser, tk_cnt
        d = copy.deepcopy(doc)
        ck = "\n".join(chunk)
        tokenize(d, pdf_parser.remove_tag(ck), pdf_parser.is_english)
        d["image"], poss = pdf_parser.crop(ck, need_position=True)
        add_positions(d, poss)
        res.append(d)
        chunk = []
        tk_cnt = 0

    while i < len(cks):
        if tk_cnt > 128: add_chunk()
        txt = cks[i]
        txt_ = pdf_parser.remove_tag(txt)
        i += 1
        cnt = num_tokens_from_string(txt_)
        chunk.append(txt)
        tk_cnt += cnt
    if chunk: add_chunk()
    for i, d in enumerate(res):
        print(d)
        # d["image"].save(f"./logs/{i}.jpg")
    return res


if __name__ == "__main__":
    import sys
    def dummy(a, b):
        pass
    chunk(sys.argv[1], callback=dummy)