from master_data.models import CompanyInfo

def company_info(request):
    info = CompanyInfo.objects.first()
    return {'company_info': info}