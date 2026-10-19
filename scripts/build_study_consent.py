"""Render the blank October guided-intake consent using optional PDF tools.

Requires reportlab and pypdf in an explicit document-authoring environment, not
application dependencies. Never overwrites a consent form. Review both rendered
pages and perform a form-fill roundtrip separately before distributing a new PDF.
This renderer preserves the original cohort and wording; changes need a reviewed
study amendment. It does not collect consent or personalize organizer details.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def _render(handle, output: Path) -> dict:
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from pypdf import PdfReader

    NAVY=colors.HexColor('#143342'); TEAL=colors.HexColor('#006C72'); GRAY=colors.HexColor('#425563')
    BODY=ParagraphStyle('body',fontName='Helvetica',fontSize=9.5,leading=13.1,textColor=NAVY)
    SMALL=ParagraphStyle('small',parent=BODY,fontSize=8.3,leading=11.2,textColor=GRAY)
    HEADING=ParagraphStyle('heading',parent=BODY,fontName='Helvetica-Bold',fontSize=11.2,leading=14,textColor=TEAL)
    W,H=612,792; M=44; CW=W-2*M
    c=canvas.Canvas(handle,pagesize=(W,H),pageCompression=1)
    c.setTitle('GEX guided intake study - participant information and consent')
    c.setAuthor('Scott Zeitner')


    def para(text,y,style=BODY,x=M,width=CW,gap=7):
        p=Paragraph(text,style);_,h=p.wrap(width,H);p.drawOn(c,x,y-h);return y-h-gap

    def field(label,name,x,y,width,height=20,multi=False):
        c.setFillColor(GRAY);c.setFont('Helvetica',8.1);c.drawString(x,y,label)
        c.acroForm.textfield(name=name,tooltip=label,x=x,y=y-height-5,width=width,height=height,
          fontName='Helvetica',fontSize=9,borderWidth=.65,borderColor=colors.HexColor('#8CA4B1'),
          fillColor=colors.HexColor('#F5FAFB'),textColor=NAVY,fieldFlags='multiline' if multi else '',forceBorder=True)
        return y-height-18

    def header(page):
        c.setFillColor(TEAL);c.rect(0,H-11,W,11,fill=1,stroke=0)
        c.setFillColor(NAVY);c.setFont('Helvetica-Bold',21);c.drawString(M,H-49,'GEX / Participant consent')
        c.setFont('Helvetica',10);c.drawString(M,H-68,'Guided intake study | 60-75 minutes | Synthetic ES/NQ')
        c.setFont('Helvetica',8);c.setFillColor(GRAY);c.drawString(M,H-85,'Cohort: guided-intake-2026-10-18-r1 | Participant delivery: v1')
        c.setStrokeColor(colors.HexColor('#BCD0D9'));c.line(M,H-96,W-M,H-96)
        c.setFont('Helvetica',8);c.drawString(M,26,'Private when completed. Return to the named study contact; keep a copy.')
        c.drawRightString(W-M,26,f'{page} / 2')
        return H-110

    def choice(title,name,description,y):
        y=para(title,y,HEADING,gap=4)
        y=para(description,y,gap=3)
        for val,x in [('Yes',M),('No',M+85)]:
            c.acroForm.radio(name=name,value=val,selected=False,tooltip=f'{title}: {val}',
              x=x,y=y-13,size=12,borderWidth=.8,borderColor=TEAL,fillColor=colors.white,textColor=NAVY,
              buttonStyle='circle',shape='circle',
              fieldFlags='noToggleToOff radio required' if name=='observation' else 'noToggleToOff radio')
            c.setFont('Helvetica',9.5);c.setFillColor(NAVY);c.drawString(x+18,y-11,val)
        return y-30

    y=header(1)
    y=para('Organizer: complete every session-detail field before asking for consent. Participant: ask about anything unclear or left blank before deciding.',y,SMALL,gap=9)
    y=field('Study contact name and monitored email','study_contact',M,y,CW)
    y=field('Moderator(s) / other people allowed to review identifiable study records','authorized_reviewers',M,y,CW)
    y=field('Incentive amount or none; terms including what happens if you stop early','incentive_terms',M,y,CW,30,True)
    y=field('Delete all organizer-held private study records by (YYYY-MM-DD)','delete_by',M,y,CW)
    y=field('Request removal by (YYYY-MM-DD; no later than the deletion date)','withdraw_by',M,y,CW)
    y=para('The organizer keeps contact details, consent and the ID link separately from task notes in private owner-controlled storage, outside the public repository and shared study kit. Only the contact and named reviewers above access identifiable records. Deletion covers organizer-held contact and scheduling records, consent, ID links, individual notes, recordings and copies. Aggregate findings without participant identifiers may be retained.',y,SMALL,gap=9)
    y=para('What you will do',y,HEADING,gap=4)
    y=para('In one remote session, you will install the supplied GEX build, share the relevant application window, try six short research tasks and discuss your experience. We use supplied synthetic ES/NQ data. The exercises need no live feed, provider login or trading. Installing dependencies may require internet access.',y)
    y=para('What we observe',y,HEADING,gap=4)
    y=para('We record task attempts, elapsed times, errors, help given, comments, relevant research experience and computer/Python setup. We may keep synthetic test receipts. Notes use a participant ID. Close unrelated windows and notifications; do not show credentials, account IDs, positions, P&amp;L, personal captures or licensed market screens. You may pause sharing at any time.',y)
    y=para('Participation and removal',y,HEADING,gap=4)
    y=para('Taking part is voluntary. You may skip a question or task, pause or stop without giving a reason. The incentive terms above apply, including an early stop. We use the observations to improve the software; identifiable quotes or recordings will not be published without separate permission. Contact the organizer by the removal date to request removal of material linked to you. After the removal window closes, aggregate findings that no longer identify you may not be separable for removal.',y)
    assert y>40,('page1 overflow',y)
    c.showPage()
    y=header(2)
    y=para('Participant ID and session details are completed by the organizer. Every choice below starts unselected. A blank optional choice gives no permission. You can participate without any recording or AI analysis.',y,SMALL,gap=10)
    left=y
    field('Participant ID','participant_id',M,left,120)
    y=field('Session date / time / time zone','session_datetime',M+136,left,CW-136)
    y=choice('1. Observation and written notes (required to take part)','observation',
     'I agree to participate in the session and let the named study team use the observations, de-identified notes and synthetic test receipts for the purposes described on page 1.',y)
    y=choice('2. Audio recording (optional)','audio_recording',
     'I allow session audio to be recorded for review by the named study team. This does not authorize automatic transcription or sending audio to an AI service.',y)
    y=choice('3. Shared-window recording (optional)','window_recording',
     'I allow the shared application window to be recorded for review by the named study team. Camera and full-desktop recording are not requested. I may ask to stop recording at any time.',y)
    y=choice('4. AI-assisted analysis of de-identified notes (optional)','ai_analysis',
     'I allow de-identified written task notes and synthetic test receipts to be supplied to ChatGPT/OpenAI to help summarize study findings. Names, contact details, audio, video and full transcripts are excluded. I may ask the organizer about the tool and data handling before choosing.',y)
    y=para('Your acknowledgment',y,HEADING,gap=4)
    y=para('I have read this information, had an opportunity to ask questions and understand that participation is voluntary. My choices above apply to this session. I will receive a copy of this completed form.',y,gap=7)
    left=y
    field('Participant name / typed acknowledgment','participant_acknowledgment',M,left,350)
    y=field('Date (YYYY-MM-DD)','participant_date',M+366,left,CW-366)
    y=para('Moderator confirmation',y,HEADING,gap=4)
    y=para('Confirm observation consent before tasks. Audio and window recording follow their separate choices; automatic transcription stays off. If silent window-only recording cannot be configured, leave recording off. AI analysis requires its separate Yes choice and removal of identifying details.',y,SMALL,gap=7)
    left=y
    field('Moderator name / acknowledgment','moderator_acknowledgment',M,left,350)
    y=field('Date (YYYY-MM-DD)','moderator_date',M+366,left,CW-366)
    assert y>40,('page2 overflow',y)
    c.save()
    handle.flush()
    reader=PdfReader(output); fields=reader.get_fields()
    assert len(reader.pages)==2
    for name in ['observation','audio_recording','window_recording','ai_analysis']:
        assert str(fields[name].get('/V','/Off'))=='/Off',(name,fields[name])
        assert bool(int(fields[name].get('/Ff',0)) & 2)==(name=='observation')
    for page in reader.pages:
        for annotation in page.get('/Annots',[]):
            d=annotation.get_object(); rect=d.get('/Rect')
            if rect: assert 0<=rect[0]<rect[2]<=W and 30<rect[1]<rect[3]<H
    return {'pages': len(reader.pages), 'fields': len(fields), 'all_choices_unselected': True}


def build(output: Path) -> dict:
    """Reserve a new output and retain failed attempts instead of overwriting."""
    with output.open("xb") as handle:
        report = _render(handle, output)
    report["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    report["visual_review"] = "not_run"
    report["form_fill_roundtrip"] = "not_run"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build(args.output)
    except (OSError, ImportError, AssertionError) as error:
        parser.exit(1, f"Consent preparation failed; retain any partial output: {error}\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
