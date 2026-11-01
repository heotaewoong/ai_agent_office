export function feedbackMessage(busy:string,error:string,notice:string) {
 if(busy)return {kind:"pending",title:`${busy} 처리 중`,message:"서버 응답을 기다리고 있습니다. 중복해서 누르지 마세요."};
 if(error)return {kind:"error",title:"요청을 완료하지 못했습니다",message:error};
 if(notice)return {kind:"success",title:"처리 결과",message:notice};
 return null;
}
