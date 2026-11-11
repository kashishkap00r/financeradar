#!/bin/bash
# One-off: can GitHub Actions reach the brokers' research pages and PDFs?
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
p() { printf "%-28s " "$1"; shift; curl -sS -m 40 -o /tmp/out -w "%{http_code} %{content_type} %{size_download}B" -H "User-Agent: $UA" -H "Accept-Language: en-US,en;q=0.9" "$@" 2>&1; echo; }
p "PL list" https://www.plindia.com/pl-research/
p "PL detail" "https://www.plindia.com/pl-research/safari-industries-india-sii-in-q2fy27-result-update-capacity-expansion-to-drive-growth-buy/"
p "PL pdf" https://plindia.com/ResReport/SII-6-11-26-PL.pdf
p "ICICI list" https://www.icicidirect.com/research/equity
p "ICICI pdf" https://mailcontent.icicidirect.com/mailcontent/idirect_titan_q2fy27.pdf
p "Kotak opportune" https://www.kotakneo.com/fundamental-research-report/opportune/
p "Kotak pdf" https://www.kotakneo.com/uploads/Aarti_Ind_One_Pager_Q2_FY_27_Result_Update_1d91911ca6.pdf
K=$(printf 12345678901234567890123456789012 | xxd -p -c 64); IV=$(printf 1234567890123456 | xxd -p)
B=$(printf '{"category_name": "fundamental", "sub_category_name": "Pick Of the Day"}' | openssl enc -aes-256-cbc -K $K -iv $IV -base64 -A)
p "SBI api" -X POST https://www.sbisecurities.in/apiconnect/research/getreports -H 'Content-Type: application/json' -H 'Origin: https://www.sbisecurities.in' -H 'Referer: https://www.sbisecurities.in/research/fundamental' -H 'client_id: no-client' --data "$B"
p "SBI pdf" "https://www.sbisecurities.in/fileserver/research/reports/Pick%20of%20the%20Day%20(Short%20Term%20Delivery%20Call)_ITC%20Hotels%20Ltd..pdf"
p "Choice api" -X POST https://finx.choiceindia.com/api/researchreport/v2/api/research-report-new -H 'Content-Type: application/json' -H 'Origin: https://choiceindia.com' -H 'Referer: https://choiceindia.com/' --data '{"end_date":"","is_expert":0,"research_type":"","limit":5,"offset":0,"segment":"EQ","start_date":"","status":"","subcategory_id":"","search":"","id":"","user_id":""}'
p "Choice pdf" "https://resrepo.choiceindia.com/researchfiles/research/2026/11/09/6af1638d0aeb9_centum-electronics_accelerating-growth-and-margin-upside-support-valuation-upgrade_nov-05,-2026.pdf"
p "Way2Wealth list" https://www.way2wealth.com/research-details/fundamental-research
p "Way2Wealth pdf" https://www.way2wealth.com/Reports/RR09112026d4ce1.pdf
p "Ventura list" https://www.ventura1.com/Research/Recommendation.aspx
p "Ventura pdf" "https://ventura1.com/calltracking/TechnicalCalls/quaterly/639298433316872389_HCC%20Result%20Update%20Q2FY27.pdf"
