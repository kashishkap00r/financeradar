#!/bin/bash
# One-off: can GitHub Actions reach round-2 broker sites?
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
p() { printf "%-26s " "$1"; shift; curl -sS -m 40 -o /tmp/out -w "%{http_code} %{content_type} %{size_download}B" -H "User-Agent: $UA" -H "Accept-Language: en-US,en;q=0.9" "$@" 2>&1 | head -c 200; echo; }
p "Arihant listing" https://arihantresearch.arihantcapital.com/Mumbai_Research/
p "Arihant pdf" https://arihantresearch.arihantcapital.com/Mumbai_Research/Voltas_Q2FY27_Result_update.pdf
p "IDBI listing" "https://www.idbidirect.in/Researchreports.aspx?Option=investment"
p "IDBI pdf" "https://www.idbidirect.in/IDBIAdmin/Pdf/TATA_RR_11112026-11-November-2026-1890400660.pdf"
p "MNCL listing (verify)" https://www.mnclgroup.com/research-reports
curl -sS -m 20 -o /tmp/r36.crt http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt && openssl x509 -inform DER -in /tmp/r36.crt -out /tmp/r36.pem && cat /etc/ssl/certs/ca-certificates.crt /tmp/r36.pem > /tmp/bundle.pem
p "MNCL listing (+R36)" --cacert /tmp/bundle.pem https://www.mnclgroup.com/research-reports
p "MNCL pdf (+R36)" --cacert /tmp/bundle.pem https://www.mnclgroup.com/storage/download/grindwel-norton-q2fy27-company-update.pdf
p "NB listing" https://www.nirmalbang.com/nb-research/institutional-research-reports.aspx
p "NB ajax page 2" "https://www.nirmalbang.com/Ajaxpages/ResearchReports.aspx?id=49&pageNo=2"
p "NB pdf" "https://www.nirmalbang.com/Upload/Fine-Organic-2QFY27-Result-Update-09-November-2026.pdf"
