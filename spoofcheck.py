import logging
from re import L
import sys
import argparse
import json

import emailprotectionslib.dmarc as dmarclib
import emailprotectionslib.spf as spflib
from colorama import Fore, Style
from colorama import init as color_init

logging.basicConfig(level=logging.INFO)


def output_good(line):
    print(Fore.GREEN + Style.BRIGHT + "[+]" + Style.RESET_ALL, line)


def output_indifferent(line):
    print(Fore.BLUE + Style.BRIGHT + "[*]" + Style.RESET_ALL, line)


def output_error(line):
    print(Fore.RED + Style.BRIGHT + "[-] !!! " + Style.NORMAL, line, Style.BRIGHT + "!!!")


def output_bad(line):
    print(Fore.RED + Style.BRIGHT + "[-]" + Style.RESET_ALL, line)


def output_info(line):
    print(Fore.WHITE + Style.BRIGHT + "[*]" + Style.RESET_ALL, line)


def check_spf_redirect_mechanisms(spf_record):
    redirect_domain = spf_record.get_redirect_domain()

    if redirect_domain is not None:
        output_info("Processing an SPF redirect domain: %s" % redirect_domain)

        return is_spf_record_strong(redirect_domain)

    else:
        return False


def check_spf_include_mechanisms(spf_record):
    include_domain_list = spf_record.get_include_domains()

    for include_domain in include_domain_list:
        output_info("Processing an SPF include domain: %s" % include_domain)

        strong_all_string = is_spf_record_strong(include_domain)

        if strong_all_string:
            return True

    return False


def is_spf_redirect_record_strong(spf_record):
    output_info("Checking SPF redirect domain: %(domain)s" % {"domain": spf_record.get_redirect_domain})
    redirect_strong = spf_record._is_redirect_mechanism_strong()
    if redirect_strong:
        output_bad("Redirect mechanism is strong.")
    else:
        output_indifferent("Redirect mechanism is not strong.")

    return redirect_strong


def are_spf_include_mechanisms_strong(spf_record):
    output_info("Checking SPF include mechanisms")
    include_strong = spf_record._are_include_mechanisms_strong()
    if include_strong:
        output_bad("Include mechanisms include a strong record")
    else:
        output_indifferent("Include mechanisms are not strong")

    return include_strong


def check_spf_include_redirect(spf_record):
    other_records_strong = False
    if spf_record.get_redirect_domain() is not None:
        other_records_strong = is_spf_redirect_record_strong(spf_record)

    if not other_records_strong:
        other_records_strong = are_spf_include_mechanisms_strong(spf_record)

    return other_records_strong


def check_spf_all_string(spf_record):
    strong_spf_all_string = True
    if spf_record.all_string is not None:
        if spf_record.all_string == "~all" or spf_record.all_string == "-all":
            output_indifferent("SPF record contains an All item: " + spf_record.all_string)
        else:
            output_good("SPF record All item is too weak: " + spf_record.all_string)
            strong_spf_all_string = False
    else:
        output_good("SPF record has no All string")
        strong_spf_all_string = False

    if not strong_spf_all_string:
        strong_spf_all_string = check_spf_include_redirect(spf_record)

    return strong_spf_all_string


def is_spf_record_strong(domain):
    strong_spf_record = True
    spf_record = spflib.SpfRecord.from_domain(domain)
    if spf_record is not None and spf_record.record is not None:
        output_info("Found SPF record:")
        output_info(str(spf_record.record))

        strong_all_string = check_spf_all_string(spf_record)
        if strong_all_string is False:

            redirect_strength = check_spf_redirect_mechanisms(spf_record)
            include_strength = check_spf_include_mechanisms(spf_record)

            strong_spf_record = False

            if redirect_strength is True:
                strong_spf_record = True

            if include_strength is True:
                strong_spf_record = True
    else:
        output_good(domain + " has no SPF record!")
        strong_spf_record = False

    return strong_spf_record


def get_dmarc_record(domain):
    dmarc = dmarclib.DmarcRecord.from_domain(domain)
    if dmarc is not None and dmarc.record is not None:
        output_info("Found DMARC record:")
        output_info(str(dmarc.record))
    return dmarc


def get_dmarc_org_record(base_record):
    org_record = base_record.get_org_record()
    if org_record is not None:
        output_info("Found DMARC Organizational record:")
        output_info(str(org_record.record))
    return org_record


def check_dmarc_extras(dmarc_record):
    if dmarc_record.pct is not None and dmarc_record.pct != str(100):
        output_indifferent("DMARC pct is set to " + dmarc_record.pct + "% - might be possible")

    if dmarc_record.rua is not None:
        output_indifferent("Aggregate reports will be sent: " + dmarc_record.rua)

    if dmarc_record.ruf is not None:
        output_indifferent("Forensics reports will be sent: " + dmarc_record.ruf)


def check_dmarc_policy(dmarc_record):
    policy_strength = False
    if dmarc_record.policy is not None:
        if dmarc_record.policy == "reject" or dmarc_record.policy == "quarantine":
            policy_strength = True
            output_bad("DMARC policy set to " + dmarc_record.policy)
        else:
            output_good("DMARC policy set to " + dmarc_record.policy)
    else:
        output_good("DMARC record has no Policy")

    return policy_strength


def check_dmarc_org_policy(base_record):
    policy_strong = False

    try:
        org_record = base_record.get_org_record()
        if org_record is not None and org_record.record is not None:
            output_info("Found organizational DMARC record:")
            output_info(str(org_record.record))

            if org_record.subdomain_policy is not None:
                if org_record.subdomain_policy == "none":
                    output_good("Organizational subdomain policy set to %(sp)s" % {"sp": org_record.subdomain_policy})
                elif org_record.subdomain_policy == "quarantine" or org_record.subdomain_policy == "reject":
                    output_bad("Organizational subdomain policy explicitly set to %(sp)s" % {
                        "sp": org_record.subdomain_policy})
                    policy_strong = True
            else:
                output_info("No explicit organizational subdomain policy. Defaulting to organizational policy")
                policy_strong = check_dmarc_policy(org_record)
        else:
            output_good("No organizational DMARC record")

    except dmarclib.OrgDomainException:
        output_good("No organizational DMARC record")

    except Exception as e:
        logging.exception(e)

    return policy_strong


def is_dmarc_record_strong(domain):
    dmarc_record_strong = False

    dmarc = get_dmarc_record(domain)

    if dmarc is not None and dmarc.record is not None:
        dmarc_record_strong = check_dmarc_policy(dmarc)

        check_dmarc_extras(dmarc)
    elif dmarc.get_org_domain() is not None:
        output_info("No DMARC record found. Looking for organizational record")
        dmarc_record_strong = check_dmarc_org_policy(dmarc)
    else:
        output_good(domain + " has no DMARC record!")

    return dmarc_record_strong

def makeDict(domain):
    spf_record_strength = is_spf_record_strong(domain)
    dmarc_record_strength = is_dmarc_record_strong(domain)
    spoofable = False 

    if (dmarc_record_strength == False):
        spoofable = True 

    dict = {'name': domain, 'spf': spf_record_strength, 'dmarc': dmarc_record_strength, 'spoofable': spoofable}

    return dict

def saveOutput(filename, results):
    try:
        fd = open(filename, 'w')
        fd.write(json.dumps(results, indent=4))
        
        fd.close()
        print(f"\n\n[*] Output file: {filename}\n\n")

    except Exception as e:
        print(f"[-] Error: {str(e)}")
        exit(1) 

def parse(parser):
    
    parser.add_argument('-d', '--domain', dest='d', type=str)
    parser.add_argument('-f', '--file', dest='f', type=str)
    parser.add_argument('-o', '--output-file', dest='o', type=str)

    if len(sys.argv) == 1:
        parser.print_help()
        exit(1)

    
    args = parser.parse_args()
    return args 

if __name__ == "__main__":
    color_init()
    parser = argparse.ArgumentParser(description="Scuffed argparse for spoofcheck")

    args = parse(parser)
    domain = args.d 
    file = args.f 
    outputFilename = args.o 
    total = 0
    spoofable = 0
    weakSPF = 0
    weakDmarc = 0
    results = []

    if (domain is not None):
        spf_record_strength = is_spf_record_strong(domain)
        dmarc_record_strength = is_dmarc_record_strong(domain)

        if dmarc_record_strength is False:
            output_good("Spoofing possible for " + domain + "!")
        else:
            output_bad("Spoofing not possible for " + domain)

    elif (file is not None):
        try:
            output_info(f"Using file: {file}\n")
            
            fd = open(file, 'r')
            for line in fd:
                total += 1 
                line = line.strip()
                output_info(f"Using: {line}")            
                results.append(makeDict(line))
                print()       
            
        except Exception as e:
            output_error(f"[-] Error: {str(e)}")

        if (outputFilename is not None):
            saveOutput(outputFilename, results)

    else:
        parser.print_help()
        exit(1)
    

    for item in results:
        if(item['spoofable'] == True):
            spoofable += 1
        if(item['spf'] == False):
            weakSPF += 1
        if(item['dmarc'] == False):
            weakDmarc += 1
        

    print("\n===============================================\n")

    print(f"[*] Total Domains: {str(total)}\n")
    print(f"[*] Weak SPF Domains: {str(weakSPF)} / {str(total)} ")
    print(f"[*] Weak DMARC Domains: {str(weakDmarc)} / {str(total)}\n")

    print(f"[*] Total Spoofable Domains: {str(spoofable)} / {str(total)}")